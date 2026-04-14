"""Quick test: check if LLM providers work."""
import asyncio, os, sys
sys.stdout.reconfigure(encoding='utf-8')
from dotenv import load_dotenv
load_dotenv()

import litellm
litellm.suppress_debug_info = True

async def test():
    providers = {
        "groq": ("groq/llama-3.1-8b-instant", "GROQ_API_KEY"),
        "mistral": ("mistral/mistral-small-latest", "MISTRAL_API_KEY"),
        "gemini": ("gemini/gemini-2.0-flash", "GEMINI_API_KEY"),
        "openrouter": ("openrouter/meta-llama/llama-3.3-70b-instruct", "OPENROUTER_API_KEY"),
    }
    
    for name, (model, key_env) in providers.items():
        key = os.environ.get(key_env, "")
        print(f"\n--- {name} ---")
        print(f"  Key: {key[:8]}...{key[-4:]}" if len(key) > 12 else f"  Key: MISSING")
        print(f"  Model: {model}")
        try:
            r = await litellm.acompletion(
                model=model,
                messages=[{"role": "user", "content": "Say hello in 5 words"}],
                max_tokens=20,
            )
            print(f"  OK: {r.choices[0].message.content.strip()}")
        except Exception as e:
            print(f"  FAIL: {str(e)[:200]}")

asyncio.run(test())
