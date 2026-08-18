# evaluate_baseline.py
# Member 1: Baseline evaluation script for AI accuracy measurement

def calculate_accuracy(tp, fp, fn):
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
    return precision, recall, f1

if __name__ == "__main__":
    print("[EVAL] Baseline evaluation script initialized.")