# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/2F. Residual (RQ) semantic token extraction model.ipynb.

# %% auto 0
__all__ = ['RQBottleneckTransformer', 'load_model', 'encode_stoks', 'extract_stoks']

# %% ../nbs/2F. Residual (RQ) semantic token extraction model.ipynb 2
import io
import time
import torch
import torchaudio

# %% ../nbs/2F. Residual (RQ) semantic token extraction model.ipynb 3
from pathlib import Path
import json
from fastprogress import progress_bar, master_bar
import fastprogress
import numpy as np
import pylab as plt
import pandas as pd

from huggingface_hub import hf_hub_download
from fastcore.basics import store_attr
import torch.nn.functional as F

from fastcore.script import *

# %% ../nbs/2F. Residual (RQ) semantic token extraction model.ipynb 27
# the model
import whisper
from torch import nn
from vector_quantize_pytorch import ResidualVQ

class LayerNorm(nn.LayerNorm):
    def forward(self, x):
        return super().forward(x.float()).type(x.dtype)
    
def sinusoids(length, channels, max_timescale=10000):
    """Returns sinusoids for positional embedding"""
    assert channels % 2 == 0
    log_timescale_increment = np.log(max_timescale) / (channels // 2 - 1)
    inv_timescales = torch.exp(-log_timescale_increment * torch.arange(channels // 2))
    scaled_time = torch.arange(length)[:, np.newaxis] * inv_timescales[np.newaxis, :]
    return torch.cat([torch.sin(scaled_time), torch.cos(scaled_time)], dim=1)

def init_transformer(m):
    if isinstance(m, (nn.Linear, nn.Embedding)):
        torch.nn.init.trunc_normal_(m.weight, std=.02)
        if isinstance(m, nn.Linear) and m.bias is not None:
            torch.nn.init.constant_(m.bias, 0)
    elif isinstance(m, nn.LayerNorm):
        torch.nn.init.constant_(m.bias, 0)
        torch.nn.init.constant_(m.weight, 1.0)

# %% ../nbs/2F. Residual (RQ) semantic token extraction model.ipynb 28
class RQBottleneckTransformer(nn.Module):
    def __init__(self, width=384, vq_codes=512, q_depth=12, depth=1, n_head=2,
                 codebook_dim=2, threshold_ema_dead_code=2, use_cosine_sim = False, kl_loss_mul=1,
                 whisper_model_name='tiny.en'):
        super().__init__()
        store_attr("codebook_dim,vq_codes,q_depth,n_head,depth,use_cosine_sim,whisper_model_name")
        
        self.kl_loss_mul = kl_loss_mul
        
        self.in_blocks = nn.Sequential(*[
            whisper.model.ResidualAttentionBlock(width, n_head) for _ in range(depth)
        ])
        self.ln_vq = LayerNorm(width)

        self.rq = ResidualVQ(
            dim = width,
            codebook_size = vq_codes, # codebook size
            decay = 0.8,              # the exponential moving average decay, lower means the dictionary will change faster
            commitment_weight = 1.,   # the weight on the commitment loss
            threshold_ema_dead_code = threshold_ema_dead_code,
            use_cosine_sim = use_cosine_sim,
            codebook_dim = codebook_dim,
            num_quantizers= q_depth,
        )
        
        self.ce_lossf = nn.CrossEntropyLoss(ignore_index=-100)
        self.kl_lossf = nn.KLDivLoss(reduction='batchmean')

        self.register_buffer("positional_embedding", sinusoids(1500, width))
        self.register_buffer("embs_padding", None)
        
        self.out_blocks = nn.Sequential(*[
            whisper.model.ResidualAttentionBlock(width, n_head) for _ in range(depth)
        ])
        self.ln_post = LayerNorm(width)
        
        self.whmodel = None
        
        self.apply(init_transformer)

    #
    # training
    #
    @torch.no_grad()
    def get_teacher_logits(self, embs, input_toks, output_toks):
        teacher_logits = whmodel.decoder(input_toks, embs)
        # set teacher logits to 0 for padding positions so KLDivLoss ignores them
        teacher_logits[output_toks == -100] = 0
        return teacher_logits
    
    def forward(self, embs, input_toks, output_toks):
        embs, input_toks, output_toks = [x.cuda() for x in [embs, input_toks, output_toks]]
        teacher_logits = self.get_teacher_logits(embs, input_toks, output_toks)
        
        # VQ bottleneck
        x = self.ln_vq(self.in_blocks(embs))
        quantized, self.indices, self.commit_loss = self.rq(x)
        self.commit_loss = self.commit_loss.mean()
        x = self.ln_post(self.out_blocks(quantized + self.positional_embedding))
        
        logits = whmodel.decoder(input_toks, x)
        self.ce_loss = self.ce_lossf(logits.view(-1,logits.shape[-1]), output_toks.view(-1))
        self.kl_loss = self.kl_lossf(F.log_softmax(logits, dim=-1), F.softmax(teacher_logits, dim=-1))
        loss = self.ce_loss + self.kl_loss_mul * self.kl_loss + self.commit_loss
        return x, loss
    
    #
    # inference
    #
    @classmethod
    def load_model(cls, repo_id="collabora/spear-tts-pytorch", filename="whisper-vq-stoks.model", local_filename=None):
        if not local_filename:
            local_filename = hf_hub_download(repo_id=repo_id, filename=filename)
        spec = torch.load(local_filename) 
        vqmodel = cls(**spec['config'])
        vqmodel.load_state_dict(spec['state_dict'])
        vqmodel.eval()
        return vqmodel
    
    def save_model(self, fname):
        torch.save(dict(config = self.__stored_args__, state_dict = self.state_dict()), fname)
        
    def ensure_whisper(self):
        assert not self.training
        if self.whmodel is None: self.whmodel = whisper.load_model(self.whisper_model_name)
        assert self.whisper_model_name.endswith('.en'), "multilingual models are not supported right now"
        self.decoding_options = whisper.DecodingOptions(language='en')
        self.tokenizer = whisper.tokenizer.get_tokenizer(False, language='en')
        silent_mel = whisper.log_mel_spectrogram(torch.zeros((1,16000*30)))
        self.embs_padding = self.whmodel.encoder(silent_mel.to(self.whmodel.device))
    
    def quantize(self, embs):
        x = self.ln_vq(self.in_blocks(embs))
        _, stoks, _ = self.rq(x)
        if self.q_depth == 1:
            stoks = stoks.squeeze(-1)
        return stoks

    def dequantize(self, stoks):
        assert self.q_depth == 1
        assert len(stoks.shape) == 1, "batch processing is not supported"
        if isinstance(stoks, np.ndarray): stoks = torch.tensor(stoks)
        # remove padding
        padding = torch.nonzero(stoks == 1024)
        if padding.any(): stoks = stoks[:padding[0,0]]
        x = self.rq.layers[0]._codebook.embed[0,stoks.to(torch.long).view(-1)]
        x = F.pad(x, (0, 0, 0, 1500-len(x)))
        x = (self.rq.layers[0].project_out(x) + self.positional_embedding).unsqueeze(0)
        return self.ln_post(self.out_blocks(x))

    def encode_audio(self, audio):
        if isinstance(audio, str):
            x, sr = torchaudio.load(audio)
            x = torchaudio.transforms.Resample(sr, 16000)(x)[0]
            audio = x.unsqueeze(0)
        return self.encode_mel(whisper.log_mel_spectrogram(audio))
    
    def encode_mel(self, mel):
        assert len(mel.shape) == 3, "invalid mel spectrogram shape, expect (batch,chn,time)"
        self.ensure_whisper()
        padded = whisper.audio.pad_or_trim(mel, whisper.audio.N_FRAMES)
        embs = self.whmodel.encoder(padded.to(self.whmodel.device))
        return self.quantize(embs)
    
    def decode_text(self, stoks, decoding_options=None):
        self.ensure_whisper()
        if decoding_options is None: decoding_options = self.decoding_options
        embs = self.dequantize(stoks).to(self.whmodel.device)
        embs = torch.cat([embs, self.embs_padding[:,embs.shape[1]:]], dim=1)
        return self.whmodel.decode(embs, decoding_options)

# %% ../nbs/2F. Residual (RQ) semantic token extraction model.ipynb 38
def load_model(fname='./vqmodel2-tiny-1000h.pth'):
    whmodel = whisper.load_model('tiny.en')
    vqmodel = RQBottleneckTransformer(codebook_dim=16, vq_codes=1024, q_depth=1, n_head=6, depth=1,
                                  threshold_ema_dead_code=0.1)
    vqmodel.load_state_dict(torch.load(fname))
    vqmodel.eval().cuda();
    return whmodel, vqmodel

# %% ../nbs/2F. Residual (RQ) semantic token extraction model.ipynb 40
from .extract_acoustic import load

def encode_stoks(whmodel, vqmodel, audio):
    """Encode the given `audio` (tensor or file name) into Whisper embeddings and lists of text tokens.
    Uses the given `whmodel` (see `load_model`).
    """
    if isinstance(audio, (Path, str)):
        audio = load(audio, newsr=whisper.audio.SAMPLE_RATE)
    mel = whisper.log_mel_spectrogram(audio[0,0])
    embs = []
    toks = []
    for start in range(0, mel.shape[-1], whisper.audio.N_FRAMES):
        sample = mel[:,start:]
        with torch.no_grad():
            padded = whisper.audio.pad_or_trim(sample, whisper.audio.N_FRAMES).unsqueeze(0)
            emb = whmodel.encoder(padded)
            toks.append(vqmodel.encode(emb).squeeze())
    return torch.stack(toks, axis=0)

# %% ../nbs/2F. Residual (RQ) semantic token extraction model.ipynb 42
@call_parse
def extract_stoks(
        srcdir:Path,  # source dir, should contain *.flac files
        outdir:Path,  # output dir, will get the *.stoks files
        model:Path,   # model path (vqmodel2-tiny-1000h.pth)
    ): 
    "Convert audio files to .stoks files quantized Whisper embeddings"
    whmodel, vqmodel = load_model(model)
        
    outdir.mkdir(exist_ok=True, parents=True)
    for name in progress_bar(list(srcdir.rglob('*.flac'))):
        stoks = encode_stoks(whmodel, vqmodel, name)
        torch.save(stoks, outdir/name.with_suffix('.stoks').name)
