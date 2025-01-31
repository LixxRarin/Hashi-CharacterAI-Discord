import socket
import json
import re
import asyncio
import datetime
import yaml
import logging

logging.basicConfig(level=logging.DEBUG, filename="app.log", format='[%(filename)s] %(levelname)s : %(message)s', encoding="utf-8")
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)  # Define o nível do console
console_handler.setFormatter(logging.Formatter('[%(filename)s] %(levelname)s : %(message)s'))

with open("config.yml", "r", encoding="utf-8") as file:
    data = yaml.safe_load(file)

async def timeout_async(func, timeout, on_timeout):
    try:
        # Aguarda a execução da função com o tempo limite especificado
        await asyncio.wait_for(func(), timeout=timeout)
    except asyncio.TimeoutError:
        # Chama a função alternativa em caso de timeout
        await on_timeout()

#Remove emojis de uma string
def remove_emoji(text):
    emoji_pattern = re.compile(
        "[\U0001F600-\U0001F64F" # emoticons
        "\U0001F300-\U0001F5FF"  # símbolos e pictogramas diversos
        "\U0001F680-\U0001F6FF"  # transporte e símbolos de mapa
        "\U0001F700-\U0001F77F"  # símbolos alquímicos
        "\U0001F780-\U0001F7FF"  # geometria e símbolos vários
        "\U0001F800-\U0001F8FF"  # símbolos de setas
        "\U0001F900-\U0001F9FF"  # emojis diversos
        "\U0001FA00-\U0001FA6F"  # símbolos e pictogramas diversos
        "\U0001FA70-\U0001FAFF"  # símbolos diversos
        "\U00002702-\U000027B0"  # símbolos adicionais
        "\U000024C2-\U0001F251"  # caracteres de cartas e quadrados
        "]+", flags=re.UNICODE)
    
    # Remove todos os emojis da frase
    return re.sub(emoji_pattern, "", text).strip()

#Testa a conecxão com a internet.
def test_internet():
    try:
        socket.create_connection(("www.google.com", 80), timeout=5)
        return True
    except OSError:
        return False

#Captura mensagens do canal especificado.
def capture_message(cache_file, message_info, reply_message=None):
    dados = read_json(cache_file)

    template_syntax = data["MessageFormatting"]["user_format_syntax"]
    reply_template_syntax = data["MessageFormatting"]["user_reply_format_syntax"]

    syntax = {
        "time" : datetime.datetime.now().strftime("%H:%M"),
        "username" : message_info["username"],
        "name" : message_info["name"],
        "message" : message_info["message"],
    }

    for pattern in data["MessageFormatting"]["remove_user_text_from"]:
        message_info["message"] = re.sub(pattern, '', message_info["message"], flags=re.MULTILINE).strip()

    if reply_message:
        syntax.update(
            {"reply_username" : reply_message["username"],
            "reply_name" : reply_message["name"],
            "reply_message" : reply_message["message"]}
        )

        for pattern in data["MessageFormatting"]["remove_user_text_from"]:
            reply_message["message"] = re.sub(pattern, '', message_info["message"], flags=re.MULTILINE).strip()

    try:

        if reply_message == None:

            msg = template_syntax.format(**syntax)
            dados.append({"Message" : msg})

        else:

            message_info = template_syntax.format(**syntax)
            reply_message = reply_template_syntax.format(**syntax) 
            dados.append({"Reply" : reply_message})

        write_json(cache_file, dados)

    except Exception as e:
        print(f"[!] Erro ao salvar mensagem no cache: {e}")

#Formata a mensagem antes de enviar para a IA.
def format_to_send(cache_file):
    format = []

    for i in cache_file:
        
        if isinstance(i, dict) and 'Message' in i:

            format.append(i["Message"])

        if isinstance(i, dict) and 'Reply' in i:

            format.append(i["Reply"])

    return "\n".join(format)

#ler arquivos Json.
def read_json(file_path):
    try:
        with open(file_path, 'r', encoding="utf-8") as file:
            return json.load(file)
    except Exception as e:
        logging.error(f"Error decoding json file {file_path}: {e}")
        return []
    
# Função de escrita do JSON
def write_json(file_path, data):
    try:
        with open(file_path, 'w', encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Error saving json file '{file_path}': {e}")
