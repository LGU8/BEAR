# ml/lstm/model.py
import torch.nn as nn


class LSTMClassifier(nn.Module):
    def __init__(self, input_dim=7, hidden_dim=64, num_classes=6):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, batch_first=True)
        self.fc = nn.Linear(hidden_dim, num_classes)

    def forward(self, x):
        _, (h_n, _) = self.lstm(x)
        out = self.fc(h_n[-1])
        return out
