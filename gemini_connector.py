import base64
import os
import google.generativeai as genai

def generate_response(input_text):
    """
    Genera una respuesta utilizando el modelo Gemini Pro
    
    Args:
        input_text (str): El texto de entrada del usuario
        
    Returns:
        Generator: Un generador que entrega chunks de la respuesta
    """
    # Configurar API key
    api_key = os.environ.get("GEMINI_API_KEY")
    genai.configure(api_key=api_key)

    # Crear modelo
    model = genai.GenerativeModel('gemini-pro')
    
    # Generar respuesta con streaming
    response = model.generate_content(
        input_text,
        stream=True
    )
    
    return response

# Función para generar con historial de conversación
def generate_with_history(messages):
    """
    Genera una respuesta utilizando el modelo Gemini Pro con historial de conversación
    
    Args:
        messages (list): Lista de mensajes de la conversación
        
    Returns:
        Generator: Un generador que entrega chunks de la respuesta
    """
    # Configurar API key
    api_key = os.environ.get("GEMINI_API_KEY")
    genai.configure(api_key=api_key)

    # Crear modelo
    model = genai.GenerativeModel('gemini-pro')
    
    # Formatear mensajes para el historial
    chat = model.start_chat(history=[])
    
    # Agregar mensajes al historial manualmente para evitar problemas con el formato
    for msg in messages:
        if msg.get('is_user', False):
            chat.history.append({
                'role': 'user',
                'parts': [{'text': msg.get('content', '')}]
            })
        else:
            chat.history.append({
                'role': 'model',
                'parts': [{'text': msg.get('content', '')}]
            })
    
    # Enviar mensaje vacío para obtener la continuación de la conversación
    response = chat.send_message('', stream=True)
    
    return response

if __name__ == "__main__":
    # Test the function
    for chunk in generate_response("¿Qué es la inteligencia artificial?"):
        print(chunk.text, end="")