# LLMX-v2
v2 of LLMX chat with gemini , claude , grok , chatgpt all at once, NO API COST , fully rendering your own profiles seamlessly inside a GUI window of which you have full control

### Set up [Linux Envirnment similar for Windows also]

## Note : Do not forget to change the webdrivers & profile path in the script

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
