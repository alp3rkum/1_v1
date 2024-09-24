from duckduckgo_search import DDGS
from flask import jsonify

# Create a DDGS object
ddgs = DDGS()

def search_web_ddg(keywords):
    results = ddgs.text(keywords,max_results=10)

    for result in results:
        print(result['title'])
        print(result['href'])
        print(result['body'])
        print("--------------------")
    
    return jsonify(results)
