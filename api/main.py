import os
import json
import zipfile
import subprocess
import re
from typing import Optional
from fastapi import FastAPI, HTTPException, Query, File, UploadFile
import httpx
import pandas as pd
from io import BytesIO
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import shutil

# Load environment variables
load_dotenv()
TOKEN = os.getenv("API_PROXY")
git_token = os.getenv("GIT_TOKEN")

# Initialize FastAPI app
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Constants
LLM_API_URL = "https://aiproxy.sanand.workers.dev/openai/v1/chat/completions"


def extract_text_from_csv(csv_file_path) -> str:
    try:
        df = pd.read_csv(csv_file_path)
        return df.to_string()
    except Exception as e:
        return f"Error reading CSV: {str(e)}"


def extract_text_from_json(json_file_path) -> str:
    try:
        with open(json_file_path, 'r', encoding='utf-8', errors='ignore') as f:
            data = json.load(f)
        return json.dumps(data, indent=2)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format.")
    except Exception as e:
        return f"Error reading JSON: {str(e)}"


def process_zip_file(zip_file_path) -> str:
    try:
        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            # Create a temporary directory for zip extraction
            tmp_dir = os.path.dirname(zip_file_path)
            extract_dir = os.path.join(tmp_dir,os.path.basename(zip_file_path).split('.')[0])
            os.makedirs(extract_dir, exist_ok=True)

            # Extract all files
            zip_ref.extractall(extract_dir)

            extracted_text = ""
            for root, _, files in os.walk(extract_dir):
                for file_name in files:
                    file_path = os.path.join(root, file_name)
                    try:
                        if file_name.endswith('.csv'):
                            extracted_text += extract_text_from_csv(file_path)
                        elif file_name.endswith('.json'):
                            extracted_text += extract_text_from_json(file_path)
                        elif file_name.endswith('.txt'):
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                extracted_text += f.read()
                    except Exception as e:
                        extracted_text += f"Error processing {file_name}: {str(e)}\n"

            return extracted_text
    except Exception as e:
        return f"Error processing ZIP file: {str(e)}"


def is_text_file(filename):
    """Check if a file is likely to be a text file based on extension"""
    text_extensions = ['.txt', '.csv', '.json', '.py', '.js', '.html', '.css', '.md', '.xml', '.yaml', '.yml']
    return any(filename.lower().endswith(ext) for ext in text_extensions)


def get_file_content(file_path):
    """Get file content, handling binary/text appropriately"""
    try:
        if is_text_file(file_path):
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        elif file_path.endswith('.zip'):
            return process_zip_file(file_path)
        else:
            return f"Binary file uploaded: {os.path.basename(file_path)}"
    except Exception as e:
        return f"Error reading file: {str(e)}"


def get_response(question: str, file_data: Optional[str] = None) -> dict:
    prompt = f"""
    You are an AI assistant that provides an answer for a given question.
    If your answer contains Python code, please provide the complete code block that can be run directly.
    The code should also print the result. In whichever question if it is asked to use any external tool 
    to perform the question return the python code for that question as a solution.If LLM is able to solve 
    the question by its own donot give python code give the final answer instead. In the python code add the 
    code to install all the required libraries using subprocess and add code to prevent showing installed libraries status like requirement already satisfied in the output screen and import it also and add code to prevent 
    ssl certification.Donot give step by step explanation just give the give code. Give it in a format so that the code can be extracted easily.
    For github based questions I want python code to use GitHub API.For GitHub username use ta1789 and Repository name use TDSProject_Test and for token use {git_token}
    For FastAPI based question use uvicorn with ip as 127.0.0.1 and port as 8002 and return the proper url in answer json and for sending any https request to a url handle the ssl certification issue like Disable SSL Verification in the httpx client by setting the verify parameter to False .
    If the code asks for vercel the code should use vercel api.Donot use sys module in subprocess.If in any question it asks to send request to OpenAI send the request to {LLM_API_URL} with the token {TOKEN}.Install the required libraries before importing it not the other way around like for example import subprocess
    import requests
    # Install required libraries
    subprocess.run(['pip', 'install', 'requests', 'PyYAML'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    here requests is imported before the subprocess code install the requests libraries this gives error so first install the libraries using subprocess and then import it and always remember to save a file by code using this tmp_dir = os.path.dirname(zip_file_path)
            extract_dir = os.path.join(tmp_dir,os.path.basename(zip_file_path).split('.')[0])
            os.makedirs(extract_dir, exist_ok=True)

    **Question**: {question}
    """

    if file_data:
        prompt += f"\n**File Content**:\n{file_data}\n"

    try:
        response = httpx.post(
            LLM_API_URL,
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}]},
            verify=False,
            timeout=30.0
        )
        response.raise_for_status()
        return response.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=500, detail=f"LLM API error: {str(e)}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid response from LLM API.")


def execute_python_code(answer: str) -> dict:
    result = {}

    # Extract Python code from response
    code_match = re.search(r'```python(.*?)```', answer, re.DOTALL)
    if code_match:
        clean_code = code_match.group(1).strip()

        # Create project-relative tmp directory path
        tmp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tmp")
        os.makedirs(tmp_dir, exist_ok=True)

        file_path = os.path.join(tmp_dir, "code.py")

        try:
            # Write extracted code to file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(clean_code)

            # Execute the script
            proc_result = subprocess.run(
                ["python", file_path],
                capture_output=True,
                text=True,
                timeout=60
            )

            # Store execution results
            result["answer"] = proc_result.stdout or "Execution complete."
            if proc_result.stderr:
                result["error"] = proc_result.stderr

        except Exception as e:
            result["error"] = str(e)

    return result


@app.post("/api/")
async def get_answer(
        question: str = Query(..., description="Question"),
        file: Optional[UploadFile] = File(None)
):
    try:
        file_data = None
        file_path = None

        if file:
            # Create temp directory if it doesn't exist
            tmp_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tmp")
            os.makedirs(tmp_dir, exist_ok=True)

            # Save the uploaded file to the temp directory
            file_path = os.path.join(tmp_dir, file.filename)

            # Save uploaded file to disk
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            # Get file content with proper handling
            file_data = get_file_content(file_path)

        response = get_response(question, file_data)

        if not response or "choices" not in response:
            raise HTTPException(status_code=500, detail="Invalid response format from LLM API.")

        answer = response["choices"][0].get("message", {}).get("content", "").strip()

        if not answer:
            raise HTTPException(status_code=500, detail="No valid answer received.")

        # If response contains Python code, execute it
        if "```python" in answer:
            return execute_python_code(answer)

        return {"answer": answer}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8001)