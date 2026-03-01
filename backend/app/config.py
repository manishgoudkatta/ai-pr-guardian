from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # GitHub
    github_webhook_secret: str = ''
    github_app_id: str = ''
    github_private_key_path: str = 'private-key.pem'
    github_token: str = ''          # PAT for local testing

    # GitHub OAuth (for multi-user login)
    github_client_id: str = ''
    github_client_secret: str = ''

    # LLM
    llm_provider: str = 'groq'      # 'groq' | 'openai' | 'ollama'
    groq_api_key: str = ''
    openai_api_key: str = ''
    ollama_base_url: str = 'http://localhost:11434'
    llm_model: str = 'llama-3.3-70b-versatile'

    # API key for GitHub Actions trigger
    review_api_key: str = ''

    # App
    app_url: str = 'http://localhost:8000'
    session_secret: str = 'change-me-in-production'

    class Config:
        env_file = '.env'
        extra = 'ignore'


settings = Settings()
