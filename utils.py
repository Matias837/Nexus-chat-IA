def get_model_settings(is_premium=False):
    """
    Returns model generation settings based on user tier
    
    Args:
        is_premium (bool): Whether the user is a premium user
        
    Returns:
        dict: Model generation settings
    """
    if is_premium:
        # Enhanced settings for premium users
        return {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 40,
            "max_output_tokens": 2048,
        }
    else:
        # Basic settings for free users
        return {
            "temperature": 0.8,
            "top_p": 0.9,
            "top_k": 20,
            "max_output_tokens": 1024,
        }
