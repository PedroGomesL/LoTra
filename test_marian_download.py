import time
from transformers import MarianMTModel, MarianTokenizer

model_name = "Helsinki-NLP/opus-mt-tc-big-en-pt"
print(f"Carregando {model_name}...")
t0 = time.time()
tokenizer = MarianTokenizer.from_pretrained(model_name)
model = MarianMTModel.from_pretrained(model_name)
print(f"Modelo carregado em {time.time() - t0:.2f}s!")

sample = "The principle of the separation of powers operates as a system of checks and balances."
inputs = tokenizer(sample, return_tensors="pt", padding=True)
gen = model.generate(**inputs, max_length=128)
trans = tokenizer.decode(gen[0], skip_special_tokens=True)
print("Tradução MarianMT:", trans)
