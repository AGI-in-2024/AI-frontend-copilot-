import logging
import os
from typing import Dict, Any
import subprocess
import json

from langchain_community.vectorstores import FAISS
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END
from langgraph.graph import StateGraph
from pydantic import BaseModel, Field
from dotenv import load_dotenv


load_dotenv()

from backend.models.prompts import code_sample, FUNNEL, INTERFACE_JSON, CODER, DEBUGGER
from backend.parsers.recursive import get_comps_descs, parse_recursivly_store_faiss

load_dotenv()


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FAISS_DB_PATH = os.path.join(BASE_DIR, "../parsers", "data", "faiss_extended")
openai_api_key = os.environ.get('OPENAI_API_KEY')
if not openai_api_key:
    raise ValueError("OPENAI_API_KEY not found in environment variables")
llm = ChatOpenAI(temperature=0.0, api_key=openai_api_key, model="gpt-4o")
embeddings = OpenAIEmbeddings(api_key=openai_api_key)
parse_recursivly_store_faiss()
db = FAISS.load_local(
    FAISS_DB_PATH, embeddings, allow_dangerous_deserialization=True
)

def format_docs(docs):
    return "\n\n".join([d.page_content for d in docs])


class Component(BaseModel):
    title: str = Field(description="название компонента НЛМК")
    reason: str = Field(description="для чего использовать на данной странице")


class FunnelOutput(BaseModel):
    needed_components: list[Component] = Field(
        description="список необходимых компонентов для реализации запроса пользователя")


class InterfaceComponent(BaseModel):
    title: str = Field(description="Название компонента")
    props: list[Dict[str, Any] | None] | Dict[str, Any] = Field(description="Список пропсов и их значений")
    used_reason: str = Field(description="Какую функцию выполняет этот компонент в данном месте")
    children: list[Dict[str, Any] | None] = Field(
        description="Список инициализированных дочерних элементов далее по иерархии ")


class InterfaceJson(BaseModel):
    initialized_components: list[InterfaceComponent]


class RefactoredInterface(BaseModel):
    fixed_code: str = Field(description="Исправленная код интерфейса")
    fixed_structure: InterfaceJson = Field(description="Исправленная JSON структура, после фикса ошибок")


class InterfaceGeneratingState(BaseModel):
    query: str | None = Field(default=None)
    components: FunnelOutput | None = Field(default=None, description="Релевантные для интерфейса компоненты")
    json_structure: InterfaceJson | None = Field(default=None, description="Структура интерфейса")
    code: str | None = Field(default=code_sample, description="Код компонента")
    errors: str | None = Field(default=None, description="Ошибки вознкшие при генерации кода")


def funnel(state: InterfaceGeneratingState):
    comps_funnel_chain = FUNNEL | llm | JsonOutputParser(pydantic_object=FunnelOutput)
    components_descs = get_comps_descs()

    res = FunnelOutput(**comps_funnel_chain.invoke(
        input={
            "query": state.query,
            "components": components_descs
        }
    ))

    # app.logger.info(f"cur state is {state}")
    print(f"\n\ncur res is {res}")
    state.components = res

    print(f"cur state {state}")
    return state


def make_structure(state: InterfaceGeneratingState):
    interface_json_chain = (
            {
                "components_info": lambda x: format_docs(
                    db.as_retriever(
                        search_type="mmr",
                        search_kwargs={
                            'k': min(len(x["needed_components"]) * 2, 15),
                            'fetch_k': min(len(x["needed_components"]) * 4, 42),
                            'lambda_mult': 0.35
                        }
                    ).invoke(str(x["needed_components"]))
                ),
                "query": lambda x: x["query"],  # Pass the question unchanged
                "needed_components": lambda x: x["needed_components"],
            }
            | INTERFACE_JSON
            | llm
            | JsonOutputParser(pydantic_object=InterfaceJson)
    )

    interface_json = interface_json_chain.invoke(
        {
            "query": state.query,
            "needed_components": state.components.needed_components
        }
    )
    state.json_structure = interface_json

    print(f"\n\ncur res is {interface_json}")
    return state


def write_code(state: InterfaceGeneratingState):
    interface_coder_chain = (
            {
                "interface_components": lambda x: format_docs(
                    db.as_retriever(
                        search_type="mmr",
                        search_kwargs={
                            'k': 10,
                            'fetch_k': 25,
                            'lamda_mult': 0.4
                        }
                    ).invoke(str(x["json_structure"]))
                ),  # Get context and format it
                "query": lambda x: x["query"],  # Pass the question unchanged
                "json_structure": lambda x: x["json_structure"],
                "code_sample": lambda x: x["code_sample"]
            }
            | CODER
            | llm
            | StrOutputParser()
    )

    interface_code = interface_coder_chain.invoke({
        "query": state.query,
        "json_structure": state.json_structure,
        "code_sample": state.code
    })

    state.code = interface_code

    print(f"\n\ncur res is {interface_code}")

    return state


def revise_code(state: InterfaceGeneratingState):
    interface_debugger_chain = (
            {
                "useful_info": lambda x: format_docs(
                    db.as_retriever(
                        search_type="similarity_score_threshold",
                        search_kwargs={
                            'k': 4,
                            'fetch_k': 20,
                            'score_threshold': 0.4
                        }
                    ).invoke(str(x["errors_list"]))
                ),  # Get context and format it
                "query": lambda x: x["query"],  # Pass the question unchanged
                "json_structure": lambda x: x["json_structure"],
                "interface_code": lambda x: x["interface_code"],
                "errors_list": lambda x: x["errors_list"]
            }
            | DEBUGGER
            | llm
            | JsonOutputParser(pydantic_object=RefactoredInterface)
    )

    fixes = interface_debugger_chain.invoke(
        {
            "query": state.query,
            "json_structure": state.json_structure,
            "interface_code": state.code,
            "errors_list": state.errors
        }
    )

    state.code = fixes.fixed_code
    state.json_structure = fixes.fixed_structure

    return state


def compile_code(state: InterfaceGeneratingState):
    try:
        print("COMPILING CODE")
        result = subprocess.run([r'D:\.dev\nodejs\npx.cmd', '--version'], capture_output=True, text=True)
        print(f"npx vers res: {result.stdout}")

        result = subprocess.run(
            [r'D:\.dev\nodejs\npx.cmd', 'ts-node', './models/compiler.tsx'],
            input=str(state.code),
            capture_output=True,
            text=True,
            check=True
        )
        print(f"{str(result.stdout)}")
        state.errors = ""
    except subprocess.CalledProcessError as e:
        print(f"Compilation error: {e.stderr}")
        state.errors = str(e.stderr)

    return state


def compile_interface(state: InterfaceGeneratingState):
    compiling_res = state.errors
    if "ERROR" in compiling_res:
        return "debug"
    else:
        # STATES_TMP_DUMP["1"] = state.model_dump()
        return END


def generate(query: str) -> str:
    cur_state = InterfaceGeneratingState(query=query)
    builder = StateGraph(InterfaceGeneratingState)
    builder.add_node("funnel", funnel)
    builder.add_node("interface", make_structure)
    builder.add_node("coder", write_code)
    builder.add_node("compiler", compile_code)
    builder.add_node("debug", revise_code)

    builder.set_entry_point("funnel")
    builder.add_edge("funnel", "interface")
    builder.add_edge("interface", "coder")
    builder.add_edge("coder", "compiler")
    builder.add_conditional_edges(
        'compiler',
        compile_interface
    )

    memory = MemorySaver()
    graph = builder.compile(checkpointer=memory)
    config = {"configurable": {"thread_id": "42"}}

    state = graph.invoke(cur_state, config)
    print("\n\n\n\nFINAL RESULT:\n")
    print(f"\t{str(state)}")

    # print(STATES_TMP_DUMP)
    code = str(state["code"])
    return code
