"""Start the commerce API."""
import os

import uvicorn
from dotenv import load_dotenv


def main():
    load_dotenv()
    uvicorn.run(
        'ai_commerce.api:create_app',
        factory=True,
        host=os.environ.get('AI_COMMERCE_HOST', '127.0.0.1'),
        port=int(os.environ.get('AI_COMMERCE_PORT', '8000')),
    )


if __name__ == '__main__':
    main()
