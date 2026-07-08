#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudmeasure_edge.occupancy_field import OccupancyMLP


def load_npz_dataset(path: Path) -> TensorDataset:
    data = np.load(path)
    query_xyz = torch.from_numpy(data["query_xyz"].astype("float32"))
    context = torch.from_numpy(data["context"].astype("float32"))
    occupancy = torch.from_numpy(data["occupancy"].astype("float32"))
    if query_xyz.shape[0] != context.shape[0] or query_xyz.shape[0] != occupancy.shape[0]:
        raise ValueError("query_xyz, context and occupancy must have matching first dimension")
    return TensorDataset(query_xyz, context, occupancy)


def train(args: argparse.Namespace) -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    dataset = load_npz_dataset(Path(args.dataset))
    loader = DataLoader(dataset, batch_size=args.batch_size, shuffle=True, num_workers=0)
    model = OccupancyMLP(hidden_dim=args.hidden_dim, depth=args.depth).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    criterion = nn.BCEWithLogitsLoss()

    for epoch in range(args.epochs):
        model.train()
        total_loss = 0.0
        total_count = 0
        for query_xyz, context, occupancy in loader:
            query_xyz = query_xyz.to(device)
            context = context.to(device)
            occupancy = occupancy.to(device)
            logits = model(query_xyz, context)
            loss = criterion(logits, occupancy)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item()) * len(query_xyz)
            total_count += len(query_xyz)
        print(f"epoch={epoch + 1} loss={total_loss / max(total_count, 1):.6f}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "model_args": {"hidden_dim": args.hidden_dim, "depth": args.depth},
            "state_dict": model.state_dict(),
        },
        output,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--epochs", type=int, default=80)
    parser.add_argument("--batch-size", type=int, default=8192)
    parser.add_argument("--hidden-dim", type=int, default=128)
    parser.add_argument("--depth", type=int, default=5)
    parser.add_argument("--lr", type=float, default=1e-3)
    train(parser.parse_args())


if __name__ == "__main__":
    main()
