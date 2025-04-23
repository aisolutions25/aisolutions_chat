import requests
import markdown

DEEPSEEK_API_KEY = 'sk-1158727f6b5f415880ca902bc851d390'

def ask_deepseek(query):
    prompt = f"""Context from attached files:
{query}

Please answer the question based on the provided context and your general knowledge."""
    
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
    data = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}]
    }
    response = requests.post(url, headers=headers, json=data)
    markdown_content = response.json()["choices"][0]["message"]["content"]
    return markdown.markdown(markdown_content)