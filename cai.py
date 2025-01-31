import asyncio
import utils
import re
from PyCharacterAI import get_client, exceptions, types
from ruamel.yaml import YAML
import logging

logging.basicConfig(level=logging.DEBUG, filename="app.log", format='[%(filename)s] %(levelname)s : %(message)s', encoding="utf-8")
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)  # Define o nível do console
console_handler.setFormatter(logging.Formatter('[%(filename)s] %(levelname)s : %(message)s'))

yaml = YAML()
yaml.preserve_quotes = True
yaml.default_flow_style=False
yaml.encoding = "utf-8"

with open("config.yml", "r", encoding="utf-8") as file:
    data = yaml.load(file)

chat_restart = data["CAI"]["new_chat_on_reset"]
answer = ""
AI_response = ""

async def get_bot_info():

    try:
        client = await get_client(token=data["CAI"]["token"])
        character = await client.character.fetch_character_info(data["CAI"]["character_id"])
    except Exception as e:
        logging.critical(f"Unable to get character information (C.AI). Error: {e}")
        input()
        exit()

    return {"name" : types.character.Character.get_dict(character)["name"], 
            "avatar_url" : types.Avatar.get_url(character.avatar)}

async def new_chat_id(create):
    if create or (data["CAI"]["chat_id"] == "---"):
        try:
            client = await get_client(token=data["CAI"]["token"])
            chat, greeting_message = await client.chat.create_chat(data["CAI"]["character_id"])
            answer = await client.chat.send_message(data["CAI"]["character_id"], chat.chat_id, data["CAI"]["system_message"])
            logging.debug(f"Character response to the system prompt: {answer.get_primary_candidate().text}")
            logging.info(f"New Chat ID: {chat.chat_id}")
            
            data["CAI"]["chat_id"] = chat.chat_id
            
            with open("config.yml", "w", encoding="utf-8") as file:
                yaml.dump(data, file)
            
            return chat.chat_id
        
        except Exception as e:
            print(f"# Erro: {e}")

    else:
        return data["CAI"]["chat_id"]

async def cai_response(cache_file):
    global chat_restart, AI_response
    
    async def try_generate():
        global answer, AI_response
    
        logging.info("Trying to generate C.AI response...")
        dados_formatados = utils.format_to_send(cache_file)
        
        MAX_TRIES = data["Options"]["max_response_attempts"]

        if MAX_TRIES <= -1:
            MAX_TRIES = len(cache_file)

        for i in range(MAX_TRIES):
            
            if not cache_file:
                logging.debug(f"No outstanding questions in {data['Discord']['messages_cache']}, generation attempt stopped.")
                break

            try:
            
                answer = await asyncio.wait_for(
                    client.chat.send_message(data["CAI"]["character_id"], data["CAI"]["chat_id"], dados_formatados),
                    timeout=10
                )
                
                AI_response = answer.get_primary_candidate().text
                logging.debug(f"Text: ({dados_formatados}) : {AI_response}")
                return  # Sai do loop após sucesso
            
            except asyncio.exceptions.TimeoutError:
                logging.debug(f"Timeout on try: {i+1}, Trying again...")
                cache_file.pop()
            except exceptions.SessionClosedError:
                logging.debug(f"Session error on try {i+1}, Trying again...")
                #cache_file.pop()
            except Exception as e:
                logging.critical(f"Unexpected error: {e}")
                break
        
        AI_response = "It was impossible to generate the message after several attempts. Check the logs.\nPossible problem with the C.AI filter."
        utils.write_json(data["Discord"]["messages_cache"], [])

    client = await get_client(token=data["CAI"]["token"])
    chat = await client.chat.fetch_chat(await new_chat_id(chat_restart))
    chat_restart = False

    while True:

        await try_generate()

        #Remove text
        for pattern in data["MessageFormatting"]["remove_IA_text_from"]:
            AI_response = re.sub(pattern, '', AI_response, flags=re.MULTILINE).strip()

        await client.close_session()
        return AI_response