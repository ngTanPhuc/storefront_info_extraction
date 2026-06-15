from ollama import chat

response = chat(
    model="qwen2.5vl:3b",
    messages=[
        {
            "role": "user",
            "content": "extract information in this image: shop name, address, phone number, website links, open hours into a json format,unknown information can be filled with null",
            "images": ["data/image.png"]
        }
    ]
)

print(response.message.content)