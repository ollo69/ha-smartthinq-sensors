# SmartThinQ LG Washer integration for HomeAssistant
A Homeassistant custom component to monitor LG Washer using SmartThinQ API (extension to other device will be managed with future development).<br/>

**Important**: The component will **not work if you have logged into the ThinQ application and registered your devices using a social network account** (google, facebook or amazon). In order to use the component you need to create a new independent LG account and make sure you log into the ThinQ app and associate your devices with it.
If during configuration you receive the message "No SmartThinQ devices found", probably your devices are still associated with the social network account. To solve the problem perform the following step:
- remove your devices from the ThinQ app
- logout from the app and login again with the independent LG account
- reconnect the devices in the app

**Note**: some device status may not be correctly detected, this depend on Washer model. I'm working to map all possible status developing the component in a way to allow to configure model option in the simplest possible way and provide update using Pull Requests. I will provide a guide on how update this information.<br/>

## Component configuration    
Once the component has been installed, you need to configure it in order to make it work.
There are two ways of doing so:
- Using the web interface (Lovelace) [**recommended**]
- Manually editing the configuration.yaml file

### Option A: Configuration using the web UI [recommended]
Simply add a new "integration" and look for "SmartThinQ LGE Washer" among the proposed ones.

Using UI you have the option to **generate a new access token** if you don't already have one. Just leave empty the token field and **follow setup worflow**.<br/>

**Important**: use your country and language code: SmartThinQ accounts are associated with a specific locale, so be sure to use the country you originally created your account with.<br/>

### Option B: Configuration via editing configuration.yaml
Follow these steps only if the previous configuration method did not work for you. 

1. Enable the component by editing the configuration.yaml file (within the config directory as well).
Edit it by adding the following lines:
    ```
    smartthinq_washer:
      token: my_smartthinq_token
      region: my_smartthinq_region (e.g. US)
      language: my_smartthinq_language (e.g. en-US)
    ```

2. Reboot HomeAssistant
