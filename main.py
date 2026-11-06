from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

app = FastAPI()

# السماح للواجهة بالاتصال بالسيرفر بدون مشاكل CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. إعدادات تحميل النموذج بضغط 4-bit مع تضمين التتوكن مباشرة
model_id = "meta-llama/Meta-Llama-3-8B-Instruct"
hf_token = "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"

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.float16
)

print("🔥 جاري تحميل النموذج باستخدام التوكن المدمج...")
tokenizer = AutoTokenizer.from_pretrained(model_id, token=hf_token)
model = AutoModelForCausalLM.from_pretrained(
    model_id,
    quantization_config=bnb_config,
    device_map="auto",
    token=hf_token
)

class PromptRequest(BaseModel):
    prompt: str

@app.get("/")
def home():
    return {"status": "WormGPT albrazily API is running 24/7"}

@app.post("/generate")
def generate_text(req: PromptRequest):
    inputs = tokenizer(req.prompt, return_tensors="pt").to("cuda" if torch.cuda.is_available() else "cpu")
    outputs = model.generate(**inputs, max_new_tokens=512)
    response_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
    return {"response": response_text}
