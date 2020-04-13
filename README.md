[![](https://img.shields.io/github/release/ollo69/ha-smartthinq-washer/all.svg?style=for-the-badge)](https://github.com/ollo69/ha-smartthinq-washer/releases)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
[![](https://img.shields.io/github/license/ollo69/ha-smartthinq-washer?style=for-the-badge)](LICENSE)
[![](https://img.shields.io/badge/MAINTAINER-%40ollo69-red?style=for-the-badge)](https://github.com/ollo69)
[![](https://img.shields.io/badge/COMMUNITY-FORUM-success?style=for-the-badge)](https://community.home-assistant.io)

# LG ThinQ Washer and Dryer integration for HomeAssistant
A Homeassistant custom component to monitor LG Washer and Dryer using ThinQ API (extension to other device will be managed with future development).<br/>

**Important Version note:** If you are upgrading to version 0.2.x from 0.1.x, it is suggested to remove component configuration
from Home Assistant before upgrade. Due to some change, if you don't remove and reconfigure, existing device will be duplicated.<br/>
***Dryer support start from version 0.2.1 and is under testing. If you have problem rollback to version 0.2.0 and wait for new release.***

**Important**: The component will **not work if you have logged into the ThinQ application and registered your devices using a social network account** (google, facebook or amazon). In order to use the component you need to create a new independent LG account and make sure you log into the ThinQ app and associate your devices with it.
If during configuration you receive the message "No SmartThinQ devices found", probably your devices are still associated with the social network account. To solve the problem perform the following step:
- remove your devices from the ThinQ app
- logout from the app and login again with the independent LG account
- reconnect the devices in the app

**Note**: some device status may not be correctly detected, this depend on Washer model. I'm working to map all possible status developing the component in a way to allow to configure model option in the simplest possible way and provide update using Pull Requests. I will provide a guide on how update this information.<br/>

## Installation
You can install this component in two ways: via HACS (as custom repository for the moment) or manually.

### Option A: Installing via HACS
If you have HACS, you must add this repository ("https://github.com/ollo69/ha-smartthinq-washer") to your Custom Repository selecting the Configuration Tab in the HACS page. Set with a category of Integration and then push save button.
After this you can go in the Integration Tab and search the "SmartThinQ LG Washer" component to install it.

### Option B: Manually installation (custom_component)
1. Clone the git master branch.
2. Unzip/copy the smartthinq_washer direcotry within the `custom_components` directory of your homeassistant installation.
The `custom_components` directory resides within your homeassistant configuration directory.
Usually, the configuration directory is within your home (`~/.homeassistant/`).
In other words, the configuration directory of homeassistant is where the configuration.yaml file is located.
After a correct installation, your configuration directory should look like the following.
    ```
    └── ...
    └── configuration.yaml
    └── secrects.yaml
    └── custom_components
        └── smartthinq_washer
            └── __init__.py
            └── config_flow.py
            └── const.py
            └── ...
    ```

    **Note**: if the custom_components directory does not exist, you need to create it.
    
3. Reboot HomeAssistant

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

## Be nice!
If you like the component, why don't you support me by buying me a coffe?
It would certainly motivate me to further improve this work.

[![Buy me a coffe!](https://www.buymeacoffee.com/assets/img/custom_images/black_img.png)](https://www.buymeacoffee.com/ollo69)
