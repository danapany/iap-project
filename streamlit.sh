#!/bin/bash
cd /home/site/wwwroot
pip install streamlit
pip install python-dotenv
pip install langchain
pip install langchain_openai
pip install langgraph
pip install langchain_community
pip install azure-core
pip install azure-search-documents
pip install azure-ai-textanalytics
pip install azure-storage-blob
pip install python-docx
pip install markdown2
pip install matplotlib
pip install bs4
pip install openai
pip install requests
pip install pandas
pip install openpyxl
python -m streamlit run src/app.py --server.port=$PORT --server.address=0.0.0.0 --server.headless=true
