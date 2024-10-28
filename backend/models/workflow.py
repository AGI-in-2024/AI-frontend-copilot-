import asyncio
import logging
import os
import re
from typing import Dict, Any, Union, List, Tuple

from langchain_community.vectorstores import FAISS
from langchain_core.output_parsers import PydanticOutputParser, StrOutputParser, CommaSeparatedListOutputParser
from langchain_core.runnables import chain
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langgraph.checkpoint.memory import MemorySaver
from langgraph.constants import END
from langgraph.graph import StateGraph
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from backend.models.prompts import code_sample, FUNNEL, CODER, DEBUGGER, FUNNEL_ITER, CODER_ITER, QUERY_GENERATOR
from backend.models.tsxvalidator.validator import TSXValidator
from backend.parsers.recursive import get_comps_descs, parse_recursivly_store_faiss

load_dotenv()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FAISS_DB_PATH = os.path.join(BASE_DIR, "../parsers", "data", "faiss_extended")
openai_api_key = os.environ.get('OPENAI_API_KEY')
try:
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY not found in environment variables")
    llm = ChatOpenAI(temperature=0.0, api_key=openai_api_key, model="gpt-4o-mini")
    embeddings = OpenAIEmbeddings(api_key=openai_api_key)
    parse_recursivly_store_faiss()

    validator = TSXValidator()
    db = FAISS.load_local(
        FAISS_DB_PATH, embeddings, allow_dangerous_deserialization=True
    )
    def_ret = db.as_retriever(
        search_type="mmr",
        search_kwargs={
            'k': 3,
            'lambda_mult': 0.42,
            'fetch_k': 30
        }
    )
    dbg_ret = db.as_retriever(
        search_kwargs={
            'k': 1
        }
    )

    memory = MemorySaver()
    components_descs = get_comps_descs()
    docs_cache = {}
except Exception as e:
    logging.error(f"{e}")


class Component(BaseModel):
    title: str = Field(description="название компонента НЛМК")
    reason: str = Field(description="для чего использовать на данной странице")


class FunnelOutput(BaseModel):
    needed_components: list[Component] = Field(
        description="Cписок необходимых компонентов для реализииции запроса пользователя")


class FunnelIterOutput(BaseModel):
    instructions: str = Field(description="Подробная инструкция по тому что нужно сделать")
    components_to_modify: list[Component] = Field(
        description="Список компонентов которые требуют модификации в имеющейся реализации")


class InterfaceGeneratingState(BaseModel):
    query: str | None = Field(default=None)
    components: list[Component] | None = Field(
        default=None,
        description="Cписок необходимых компонентов для реализииции запроса пользователя"
    )
    code: str | None = Field(default=code_sample, description="Код компонента")
    errors: str | None | list[Any] = Field(default=None, description="Ошибки вознкшие при генерации кода")

    new_query: str | None = Field(default=None, description="Новый запрос для изменения текущего интерфейса")
    instructions: str | None = Field(
        default=None,
        description="Подробная инструкция по тому как улучшить интерфейс"
    )
    components_to_modify: list[Component] | None = Field(
        default=None,
        description="Список компонентов которые требуют модификации в имеющейся реализации"
    )


async def funnel(state: InterfaceGeneratingState):
    logging.info(f"Funnel...")
    if llm is None:
        state.errors = "LLM not initialized properly"
        return state
    if state.new_query:
        iter_funnel_chain = FUNNEL_ITER | llm | PydanticOutputParser(pydantic_object=FunnelIterOutput)
        res = iter_funnel_chain.invoke(
            input={
                "previous_query": state.query,
                "new_query": state.new_query,
                "existing_code": state.code,
                "components": components_descs
            }
        )

        state.instructions = res.instructions
        state.components_to_modify = res.components_to_modify
    else:
        funnel_chain = FUNNEL | llm | PydanticOutputParser(pydantic_object=FunnelOutput)
        res = funnel_chain.invoke(
            input={
                "query": state.query,
                "components": components_descs
            }
        )

        state.components = [cmp for cmp in res.needed_components if f'{cmp.title}:' in components_descs]
    logging.info(f"Needed components: {state.components}")
    return state


async def search_docs(queries: list[str], is_dbg: bool = False):
    logging.info(f"Looking for cached queries in {len(docs_cache)}...")

    def truncate_content(content):
        sentences = content.splitlines()
        if len(sentences) > 250:
            content = '\n'.join(sentences[:250]) + '...'
        return content

    retriever = (def_ret, dbg_ret)[is_dbg]

    dbg = {}
    qrs, docs = [], []
    queries = set(queries)
    for q in queries:
        if q in docs_cache:
            docs.append(docs_cache[q])
            dbg[q] = docs_cache[q]
        else:
            qrs.append(q)
    logging.info(f"Retrieving {len(qrs)} queries...")
    if qrs:
        tasks = [retriever.ainvoke(query) for query in qrs]
        results = await asyncio.gather(*tasks)

        for i, result in enumerate(results):
            for doc in result:
                doc.page_content = truncate_content(doc.page_content)
            docs += result
            docs_cache[qrs[i]] = result
            dbg[qrs[i]] = result

    logging.info(f"{len(docs)} docs collected.")
    logging.info(dbg)
    logging.info('*' * 50)
    return docs


async def write_code(state: InterfaceGeneratingState):
    logging.info(f"Writer...")
    interface_coder_chain = (
            {
                "interface_components": lambda x: x["interface_components"],
                "query": lambda x: x["query"],
                "code_sample": lambda x: x["code_sample"]
            }
            | CODER
            | llm
            | StrOutputParser()
    )
    interface_coder_iter_chain = (
            {
                "interface_components": lambda x: x["interface_components"],
                "query": lambda x: x["query"],
                "new_query": lambda x: x["new_query"],
                "instructions": lambda x: x["instructions"],
                "existing_code": lambda x: x["existing_code"]
            }
            | CODER_ITER
            | llm
            | StrOutputParser()
    )

    if state.new_query:
        interface_code = interface_coder_iter_chain.invoke({
            "query": state.query,
            "new_query": state.new_query,
            "existing_code": state.code,
            "instructions": state.instructions,
            "interface_components": await search_docs(
                [f"Detailed ARG TYPES of props a component {x.title} can have and CODE examples of using {x.title}"
                 for x in state.components_to_modify]
            )
        })
    else:
        interface_code = interface_coder_chain.invoke({
            "query": state.query + str(state.components),
            "code_sample": state.code,
            "interface_components": await search_docs(
                [f"Detailed argsTypes, index and props of a component {x.title} can have and CODE examples of using {x.title}"
                 for x in state.components]
            )
        })

    state.code = interface_code
    logging.info(f"Written code: {state.code}")
    return state


async def debug_docs(code: str, errors_list: list[Dict[str, Any]]) -> tuple[str, list[Any] | str]:
    logging.info(f"Making queries for fixing...")
    queries = []
    code_lines = code.splitlines()
    pattern = r'\W([A-Z]{2}[a-z]+)'

    for error in errors_list:
        line_num = error['location'][0] - 1
        error_message = f"//ERROR {error['code']}: {error['message']}"
        matches = set(re.findall(pattern, error['message']))
        if matches:
            queries += matches
        elif len(queries) < 3:
            queries.append(f'useful code samples to fix {error['message']}')
        if line_num < len(code_lines):
            code_lines[line_num] = code_lines[line_num] + error_message
        else:
            code_lines.append(error_message)

    annotated_code = f"code with error messages :\n" + "\n".join(code_lines)
    logging.info(f"{queries}")
    docs = await search_docs(queries, True) if queries else "No special information needed to fix these errors"

    return annotated_code, docs


async def revise_code(state: InterfaceGeneratingState):
    logging.info(f"Reviser...")
    interface_debugger_chain = (
            {
                "useful_info": lambda x: x["useful_info"],  # Передаём найденные доки по ошибкам
                "interface_code": lambda x: x["interface_code"]
            }
            | DEBUGGER
            | llm
            | StrOutputParser()
    )
    code, docs = await debug_docs(state.code, state.errors)
    logging.info(f"rewriting code...")
    logging.info(code)

    fixed_code = interface_debugger_chain.invoke(
        {
            "interface_code": code,
            "useful_info": docs
        }
    )

    state.code = fixed_code
    logging.info(f"Revised code: {state.code}")
    return state


async def compile_code(state: InterfaceGeneratingState):
    logging.info(f"compile node...")
    state.code = re.sub(r"```(jsx|tsx)\s*|\s*```", "", state.code)
    validation_result = validator.validate_tsx(state.code.strip())

    if validation_result["valid"]:
        state.errors = ""
        if state.new_query:
            state.query = state.query + state.new_query
    else:
        state.errors = validation_result["errors"]
    logging.info(f"compiling completed.")
    return state


async def compile_interface(state: InterfaceGeneratingState):
    compiling_res = state.errors
    if not compiling_res:
        return END
    else:
        return "debug"


async def generate(query: str) -> str:
    logging.info(f"generate func started")

    try:
        # Set up configuration with retry mechanism
        config = {
            "configurable": {"thread_id": "42"},
            "recursion_limit": 50,  # Increase the number of retries further
        }
        cur_state = None
        if memory.get_tuple(config):
            cur_dict: dict = memory.get_tuple(config)[1]["channel_values"]
            cur_state = InterfaceGeneratingState(**cur_dict)

            # add new button for iterative process
            # cur_state.new_query = query
            cur_state.query = query
        if not cur_state:
            cur_state = InterfaceGeneratingState(query=query)

        builder = StateGraph(InterfaceGeneratingState)
        builder.add_node("funnel", funnel)
        builder.add_node("coder", write_code)
        builder.add_node("compiler", compile_code)
        builder.add_node("debug", revise_code)

        builder.set_entry_point("funnel")
        builder.add_edge("funnel", "coder")
        builder.add_edge("coder", "compiler")
        builder.add_conditional_edges(
            'compiler',
            compile_interface
        )
        builder.add_edge("debug", "compiler")
        graph = builder.compile(checkpointer=memory)

        try:
            logging.info(f"graph invoking...")
            state = await graph.ainvoke(cur_state, config)
            logging.info("Generation process completed successfully.")
            if isinstance(state, dict):
                logging.info(f"Final state errors: {state.get('errors', 'No errors')}")
                logging.info(f"Final state code length: {len(state.get('code', ''))}")
                return str(state.get('code', 'No code generated'))
            else:
                logging.error(f"Unexpected state type: {type(state)}")
                return "An error occurred: Unexpected state type"
        except EnvironmentError as e:
            logging.error(f"Environment setup error: {str(e)}")
            return f"An error occurred during environment setup: {str(e)}"
        except Exception as e:
            logging.error(f"Error in generate function: {str(e)}")
            return f"An error occurred during generation: {str(e)}"
    except Exception as e:
        logging.error(f"Error in generate function: {str(e)}")
        return f"An error occurred during generation: {str(e)}"


def _add_error_handling(func):
    def wrapper(state: InterfaceGeneratingState):
        try:
            return func(state)
        except Exception as e:
            logging.error(f"Error in {func.__name__}: {str(e)}")
            state.errors = f"Error in {func.__name__}: {str(e)}"
            return state

    return wrapper
