# LLMX-v2
An AI council powered by llmx v2 - Chat with Claude, ChatGPT, Grok, Gemini all at once, NO extra API COST , fully rendering your own profiles seamlessly inside a GUI window of which you have full control

<img width="1919" height="956" alt="Screenshot From 2026-05-19 01-27-58" src="https://github.com/user-attachments/assets/26fc2252-ce53-44a0-b906-1862de360dac" />

# Installation 

1. Clone the repo
```
git clone https://github.com/computerauditor/LLMX-v2/
```

#  SET UP [Linux Envirnment similar for Windows also]

2. Create virtual environment [OPTIONAL but recommended]

Linux / macOS :
```
python3 -m venv venv
source venv/bin/activate
```
Windows : 
```
python -m venv venv
venv\Scripts\activate
```
3. Install dependencies
```
pip install -r requirements.txt
```

Webdriver Setup

Place your GeckoDriver[For FireFox] binary inside:
```
webdrivers/geckodriver
```
Linux users may need to give permission to the webdrivers by :

FireFox
```
chmod +x webdrivers/geckodriver
```
Chrome
```
chmod +x webdrivers/chromedriver
```

Download GeckoDriver:
```
https://github.com/mozilla/geckodriver/releases
```

## Note : Do not forget to change the webdrivers & profile path in the script
Update these paths in main.py:

REAL_CHROME_PROFILE = "/path/to/chrome/profile"
REAL_FIREFOX_PROFILE = "/path/to/firefox/profile"

# ChromeDrivers

Create an isolated profile just for web scrapping 

lets say ~/chrome-profiles/selenium-profile/
```
google-chrome --user-data-dir="$HOME/chrome-profiles/selenium-profile"
```
(or can use chromium)

Do one time login into services such as Google,Gemini,ChatGPT,Claude,Grok etc
```
google-chrome --user-data-dir="$HOME/chrome-profiles/selenium-profile" --password-store=basic
```
This will save your session for future reference

Then run the script and voila!!! 
```
python llmx.py
```
# FireFox

create a new profile in firefox

```
about:profiles
```
Do one time login into services such as Google,Gemini,ChatGPT,Claude,Grok etc
Then run the script  
```
python llmx.py
```

Note : Cloudeflare protection can be hindered on firefox cause the gecko drivers are easily detected but gemini and grok works fine though you may have issues with claude and chatGPT
but use can try different flags in the firefox section of the script to tweak settings.
