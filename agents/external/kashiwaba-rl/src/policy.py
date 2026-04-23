from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn as nn


@dataclass(slots=True)
class PolicyOutput:
    target_logits: torch.Tensor
    value: torch.Tensor


class PlanetPolicy(nn.Module):
    def __init__(
        self,
        self_dim: int,
        candidate_dim: int,
        global_dim: int,
        candidate_count: int,
        hidden_size: int = 128,
    ) -> None:
        super().__init__()
        self.candidate_count = candidate_count
        self.self_encoder = nn.Sequential(
            nn.Linear(self_dim, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
        )
        self.global_encoder = nn.Sequential(
            nn.Linear(global_dim, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
        )
        self.candidate_encoder = nn.Sequential(
            nn.Linear(candidate_dim, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, hidden_size),
            nn.ReLU(),
        )
        self.target_head = nn.Sequential(
            nn.Linear(hidden_size * 3, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, 1),
        )
        self.value_head = nn.Sequential(
            nn.Linear(hidden_size * 3, hidden_size),
            nn.ReLU(),
            nn.Linear(hidden_size, 1),
        )

    def forward(
        self,
        self_features: torch.Tensor,
        candidate_features: torch.Tensor,
        global_features: torch.Tensor,
        candidate_mask: torch.Tensor,
    ) -> PolicyOutput:
        self_hidden = self.self_encoder(self_features)
        global_hidden = self.global_encoder(global_features)
        candidate_hidden = self.candidate_encoder(candidate_features)
        expanded_self = self_hidden.unsqueeze(1).expand(-1, self.candidate_count, -1)
        expanded_global = global_hidden.unsqueeze(1).expand(-1, self.candidate_count, -1)
        joint = torch.cat([expanded_self, expanded_global, candidate_hidden], dim=-1)
        target_logits = self.target_head(joint).squeeze(-1)
        target_logits = target_logits.masked_fill(~candidate_mask, torch.finfo(target_logits.dtype).min)
        pooled_candidates = candidate_hidden.mean(dim=1)
        value = self.value_head(torch.cat([self_hidden, global_hidden, pooled_candidates], dim=-1)).squeeze(-1)
        return PolicyOutput(target_logits=target_logits, value=value)
