import os
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS  # Import CORS
import traceback
from langchain_openai import ChatOpenAI   # Import GPT-4
from langchain_openai import ChatOpenAI   # Import GPT-4
from langchain_core.messages import HumanMessage, SystemMessage

from backend.models.workflow import generate
from backend.models.prompts import get_ui_improvement_prompt  # Import the new function
from backend.models.prompts import get_ui_description_prompt
from backend.models.prompts import get_quick_improve_prompt
from backend.models.prompts import get_ui_improvement_prompt  # Import the new function
from backend.models.prompts import get_ui_description_prompt
from backend.models.prompts import get_quick_improve_prompt

app = Flask(__name__)
CORS(app)  # This will allow all origins

smart_llm = ChatOpenAI(
    model="gpt-4o",
    temperature=0,
    max_tokens=4000,
    timeout=None,
    max_retries=2,
    api_key=os.environ.get('OPENAI_API_KEY')
)

fast_llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    max_tokens=4000,
    timeout=None,
    max_retries=2,
    api_key=os.environ.get('OPENAI_API_KEY')
)

@app.route('/generate', methods=['POST'])
async def generate_ui():
    app.logger.info("Received request to /generate")
    data = request.json
    app.logger.info(f"Received data: {data}")

    if not data or 'question' not in data:
        return _handle_invalid_request()
        return _handle_invalid_request()

    question = data['question']

    try:
        result = await _process_question(question)
        response = _invoke_llm(str(result), question)  # Pass the code to _invoke_llm
        return jsonify({"result": response.content})
    except Exception as e:
        return _handle_exception(e)

def _handle_invalid_request():
    app.logger.error("Invalid or missing question in request")
    return jsonify({"error": "Invalid or missing question in request"}), 400

async def _process_question(question):
    app.logger.info(f"Processing question: {question}")
    result = await generate(question)
    app.logger.info(f"Generated result: {result[:100]}...")  # Log first 100 chars
    # return jsonify({"result": result})
    return result

def _invoke_llm(result, question):  # Change to synchronous function
    prompt = get_ui_improvement_prompt(result, question)
    return smart_llm.invoke([
        SystemMessage(content="You are a senior React developer."),
        HumanMessage(content=prompt)
    ])

def _handle_exception(e):
    app.logger.error(f"Error in generate_ui: {str(e)}")
    app.logger.error(f"Traceback: {traceback.format_exc()}")
    return jsonify({"error": f"An error occurred: {str(e)}"}), 500

# Add this new route for debugging
@app.route('/debug', methods=['POST'])
def debug_request():
    data = request.json
    app.logger.info(f"Debug request received: {data}")
    return jsonify({
        "received_data": data,
        "content_type": request.content_type,
        "headers": dict(request.headers)
    })


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({"status": "healthy"}), 200


@app.route('/update-preview', methods=['POST', 'OPTIONS'])
def update_preview():
    if request.method == "OPTIONS":
        return _build_cors_preflight_response()
    elif request.method == "POST":
        code = request.json['code']
        file_path = os.path.join(os.getcwd(), 'vite-preview-mode', 'my-app', 'src', 'Home', 'GeneratedComponent.tsx')

        try:
            directory = os.path.dirname(file_path)
            if not os.path.exists(directory):
                os.makedirs(directory)
                app.logger.info(f"Created directory: {directory}")

            with open(file_path, 'w') as file:
                file.write(code)
            app.logger.info(f"Successfully wrote to file: {file_path}")
            return _corsify_actual_response(jsonify({"message": "Code updated successfully"}))
        except Exception as e:
            error_message = f"Error updating file: {str(e)}\n{traceback.format_exc()}"
            app.logger.error(error_message)
            return _corsify_actual_response(jsonify({"error": error_message}), 500)

def _build_cors_preflight_response():
    response = make_response()
    response.headers.add("Access-Control-Allow-Origin", ALLOWED_ORIGINS[0])  # Use the first origin
    response.headers.add('Access-Control-Allow-Headers', "Content-Type")
    response.headers.add('Access-Control-Allow-Methods', "POST, OPTIONS")
    return response

def _corsify_actual_response(response, status_code=200):
    response.headers.add("Access-Control-Allow-Origin", ALLOWED_ORIGINS[0])  # Use the first origin
    return response, status_code

@app.route('/generate-description', methods=['POST'])
async def generate_description():
    app.logger.info("Received request to /generate-description")
    data = request.json
    app.logger.info(f"Received data: {data}")

    if not data or 'question' not in data:
        return _handle_invalid_request()

    question = data['question']

    try:
        response = _invoke_llm_for_description(question)
        return jsonify({"result": response.content})
    except Exception as e:
        return _handle_exception(e)

def _invoke_llm_for_description(question):
    prompt = get_ui_description_prompt(question)
    return fast_llm.invoke([
        SystemMessage(content="You are a UI/UX expert specializing in creating detailed interface descriptions. Your description will be used to generate react code with nlmk components."),
        HumanMessage(content=prompt)
    ])

@app.route('/quick-improve', methods=['POST'])
async def quick_improve():
    app.logger.info("Received request to /quick-improve")
    data = request.json
    app.logger.info(f"Received data: {data}")

    if not data or 'code' not in data or 'design' not in data or 'modification' not in data:
        return _handle_invalid_request()

    code = data['code']
    design = data['design']
    modification = data['modification']

    try:
        response = _invoke_llm_for_quick_improve(code, design, modification)
        return jsonify({"result": response.content})
    except Exception as e:
        return _handle_exception(e)

def _invoke_llm_for_quick_improve(code, design, modification):
    prompt = get_quick_improve_prompt(code, design, modification)
    return smart_llm.invoke([
        SystemMessage(content="You are a senior React developer specializing in improving and optimizing React code."),
        HumanMessage(content=prompt)
    ])

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
