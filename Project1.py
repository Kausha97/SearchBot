import asyncio
import json
import subprocess
import urllib.parse
from datetime import datetime
from typing import Dict, List, Any, Optional
import requests
from bs4 import BeautifulSoup
from gtts import gTTS
import urllib.parse
import re


class ChatBot:
    """
    A chatbot class that interacts with a local Llama model using Ollama.
    """

    def __init__(self) -> None:
        """Initialize the ChatBot instance with a conversation history."""
        self.history: List[Dict[str, str]] = [{"role": "system", "content": "You are a helpful assistant."}]
        print("ChatBot instance initialized")

    def generate_response(self, prompt: str) -> str:
        """
        Generate a response from the chatbot based on the user's prompt.

        Args:
            prompt (str): The input message from the user.

        Returns:
            str: The chatbot's response to the provided prompt.
        """
        self.history.append({"role": "user", "content": prompt})
        conversation = "\n".join(f"{msg['role']}: {msg['content']}" for msg in self.history)

        try:
            # Run the Llama model using Ollama
            completion = subprocess.run(
                ["ollama", "run", "llama3.2:latest"],
                input=conversation,
                capture_output=True,
                text=True,
                encoding="utf-8"
            )

            proc = subprocess.Popen(
                ["ollama", "run", "llama3.2"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            completion = proc.communicate(input=prompt)

            if completion.returncode != 0:
                print(f"Error running subprocess: {completion.stderr}")
                return "I'm sorry, I encountered an issue processing your request."

            response = completion.stdout.strip()
            self.history.append({"role": "assistant", "content": response})
            return response

        except Exception as e:
            print(f"Error sending query to the model: {e}")
            return "I'm sorry, an error occurred while processing your request."

    async def rate_body_of_article(self, article_title: str, article_content: str) -> str:
        """
        Rate the quality of an article's content based on its title.
        """
        prompt = f"""
           Given the following article title and content, provide a rating between 1 and 5.
           - Article Title: {article_title}
           - Article Content: {article_content[:1000]}...
           Output only a single integer between 1 and 5.
           """

        try:
            completion = subprocess.run(
                ["ollama", "run", "llama3.2:latest"],
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8"
            )

            print(f"Prompt sent:\n{prompt}")
            print(f"Ollama output:\n{completion.stdout}")

            if completion.returncode != 0:
                print(f"Error running subprocess: {completion.stderr}")
                return "Error"

            response = completion.stdout.strip()

            # Use regex to extract a digit between 1 and 5.
            rating_match = re.search(r'\b([1-5])\b', response)
            if rating_match:
                return rating_match.group(1)
            else:
                print(f"Unexpected response format: {response}")
                return "Error"

        except Exception as e:
            print(f"Error sending query to the model: {e}")
            return "Error"

def clean_url(url: str) -> str:
    """Extracts the actual article URL from DuckDuckGo's redirection link."""
    if "uddg=" in url:
        parsed_url = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        return parsed_url["uddg"][0] if "uddg" in parsed_url else url
    return url


def extract_news_body(news_url: str) -> str:
    """Extract the full article body from a given news URL."""
    try:
        news_url = clean_url(news_url)  # Clean the URL before requesting
        headers = {"User-Agent": "Mozilla/5.0"}
        response = requests.get(news_url, headers=headers, timeout=5)

        if response.status_code != 200:
            print(f"Failed to fetch article: {response.status_code}")
            return "Failed to fetch article."

        soup = BeautifulSoup(response.text, "html.parser")

        # Try extracting article content in multiple ways
        paragraphs = soup.find_all("p")
        if not paragraphs:
            return "No readable content found."

        article_content = "\n".join([p.text.strip() for p in paragraphs if p.text.strip()])
        print(f"Article content extracted from {news_url}")
        return article_content[:5000]  # Limit to 5000 characters for efficiency
    except Exception as e:
        print(f"Error extracting article content: {e}")
        return f"Error extracting article content: {e}"

async def invoke_duckduckgo_news_search(query: str, num: int = 5) -> Dict[str, Any]:
    """Perform a DuckDuckGo News search and process articles asynchronously."""
    print(f"Starting DuckDuckGo news search for query: {query}")

    search_url = f"https://html.duckduckgo.com/html?q={query.replace(' ', '+')}&kl=us-en&df=w&ia=news"
    headers = {"User-Agent": "Mozilla/5.0"}

    response = requests.get(search_url, headers=headers)
    if response.status_code != 200:
        return {"status": "error", "message": "Failed to fetch news search results"}

    soup = BeautifulSoup(response.text, "html.parser")
    search_results = soup.find_all("div", class_="result__body")

    async def process_article(result, index: int) -> Optional[Dict[str, Any]]:
        """Processes a single article: extracts details, fetches content, and rates it."""
        try:
            title_tag = result.find("a", class_="result__a")
            if not title_tag:
                return None

            title = title_tag.text.strip()
            raw_link = title_tag.get("href", "")

            if "uddg=" in raw_link:
                link = clean_url(raw_link)
            else:
                link = raw_link

            snippet_tag = result.find("a", class_="result__snippet")
            summary = snippet_tag.text.strip() if snippet_tag else "No summary available."

            article_content = extract_news_body(link)

            bot = ChatBot()
            rating = await bot.rate_body_of_article(title, article_content)

            return {"num": index + 1, "link": link, "title": title, "summary": summary, "body": article_content, "rating": rating}
        except Exception as e:
            return None

    tasks = [process_article(result, index) for index, result in enumerate(search_results[:num])]
    extracted_results = await asyncio.gather(*tasks)
    extracted_results = [res for res in extracted_results if res is not None]

    if extracted_results:
        return {"status": "success", "results": extracted_results}
    else:
        return {"status": "error", "message": "No valid news search results found"}


def save_to_audio(text: str) -> None:
    """Converts text to an audio file using Google Text-to-Speech (gTTS)."""
    try:
        tts = gTTS(text=text, lang="en")
        tts.save("output.mp3")
        print("Response converted to audio")
    except Exception as e:
        print(f"Error converting response to audio: {e}")


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    search_results = loop.run_until_complete(invoke_duckduckgo_news_search("Python programming", num=1))
    print(json.dumps(search_results, indent=2))