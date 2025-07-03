from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

MODEL_NAME = "beomi/beep-KcELECTRA-base-hate"
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModelForSequenceClassification.from_pretrained(MODEL_NAME)

labels = ['none', 'offensive', 'hate']

def predict_label(text: str) -> dict:
    inputs = tokenizer(text, return_tensors="pt", truncation=True, padding=True)
    with torch.no_grad():
        outputs = model(**inputs)
        probs = torch.softmax(outputs.logits, dim=-1).squeeze()
    result = {label: float(probs[i]) for i, label in enumerate(labels)}
    result['predicted'] = labels[probs.argmax().item()]
    return result