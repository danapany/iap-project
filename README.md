# README.md

# Streamlit Notes Application

This project is a simple Streamlit application that allows users to organize and display notes in a structured format, similar to Notion.

## Project Structure

```
streamlit-project
├── src
│   └── app.py                  # Main
│       └── menu                # Menus
│           ├── 1_Chatbot.py    # Guide
│           └── 2_FAQ.py                                         # View FAQ
│           └── 3_Suggestions for improvement.py                 # View Suggestions for improvement
│           └── 91_#_Admin-Process_Description_Create.py         # Create Process Description
│           └── 92_#_Admin-FAQ_Create.py                         # Create FAQ
│           └── 93_#_Admin-Keyword-based_question_Create.py      # Process the layout of the application
│           └── 94_#_Admin-Suggestions for improvement_Create.py # Create Suggestions for improvement
│           └── 99_#_ktds_API_KEY_Create.py                      # ktds API KEY Generator
└── data
    └── pdfs                 # Training datas
    └── db                   # DB datas
├── requirements.txt         # Lists the dependencies for the project
└── README.md                # Documentation for the project
```

## Installation

   # Install Library
   pip install -r requirements.txt

   # If a virtual environment error occurs
   python -m ensurepip --upgrade
   python -m pip install --upgrade pip

## Overview of the App

This app showcases a growing collection of LLM minimum working examples.

Current examples include:

- Chatbot
- Process Description
- FAQ
- Suggestions for improvement

- (Admin) Create Process Description
- (Admin) Create FAQ
- (Admin) Create Keyword-based_question for Chatbot
- (Admin) Create Suggestions for improvement
- (ktds) Create ktds API KEY for future system expansion


1. Clone the repository:
   ```
   git clone <repository-url>
   cd streamlit-project
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

## Running the Application

To run the Streamlit application, execute the following command in your terminal:
```
streamlit run src/Chatbot.py
```

## Usage

Once the application is running, you can view and interact with your notes in the web browser. The layout is designed to be user-friendly and allows for easy navigation through different sections of notes.

## Contributing

Feel free to submit issues or pull requests if you have suggestions or improvements for the project.