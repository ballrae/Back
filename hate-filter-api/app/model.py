from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

MODEL_NAME = "p3ngdump/koelectra-hate-speech"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)
model.eval()

labels = ["none", "offensive", "hate"]

def predict_label_batch(texts: list[str]) -> list[dict]:
    if not texts:
        return []

    # GPU 사용 가능하면 이동
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model.to(device)

    inputs = tokenizer(
        texts,
        return_tensors="pt",
        truncation=True,
        padding=True,
        max_length=128
    ).to(device)

    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.softmax(outputs.logits, dim=-1)

    preds = torch.argmax(probs, dim=1)
    results = []
    for i, prob in enumerate(probs):
        result = {label: float(prob[j]) for j, label in enumerate(labels)}
        result['predicted'] = labels[preds[i].item()]
        results.append(result)

    return results