# LG ThinQ Devices integration for HomeAssistant
A Homeassistant custom component to monitor LG Washer, Dryer, DishWasher and Refrigerators using ThinQ API
based on [WideQ project][wideq].<br/>

**Important Version note:** 
1. From version 0.3.x component name changed from `smartthinq_washer` to `smartthinq_sensors`
If you are upgrading to version 0.3.x from previous version, you must **remove component configuration and uninstall component**
from Home Assistant before upgrade.<br/>

2. From version 0.5.x devices state labels are loaded from "language pack" and shown in the language related to your account.
This change should solve all case of "unknown state" warning, due to the big change some sensors may not work as expected.
Please open issue with all possible detail to help me to fix possible new issues introduced.

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
Simply add a new "integration" and look for "SmartThinQ LGE Sensors" among the proposed ones and
**follow setup worflow**.<br/>

**Important**: use your country and language code: SmartThinQ accounts are associated with a specific locale, so be sure to use the country you originally created your account with.<br/>

### Option B: Configuration via editing configuration.yaml [deprecated]
Follow these steps only if the previous configuration method did not work for you.<br/>
**Note**: with this configuration the integration will use APIv1 that cannot connect to new LG devices.
This configuration option is deprecated and will be removed in future versions<br/>

1. Enable the component by editing the configuration.yaml file (within the config directory as well).
Edit it by adding the following lines:
    ```
    smartthinq_sensors:
      token: my_smartthinq_token
      region: my_smartthinq_region (e.g. US)
      language: my_smartthinq_language (e.g. en-US)
    ```

2. Reboot HomeAssistant

## Be nice!
If you like the component, why don't you support me by buying me a coffe?
It would certainly motivate me to further improve this work.

[![Buy me a coffe!](https://www.buymeacoffee.com/assets/img/custom_images/black_img.png)](https://www.buymeacoffee.com/ollo69)

Credits
-------

This component is developed by [Ollo69][ollo69] based on [WideQ API][wideq].<br/>
Original WideQ API was developed by [Adrian Sampson][adrian] under license [MIT][].

[ollo69]: https://github.com/ollo69
[wideq]: https://github.com/sampsyo/wideq
[adrian]: https://github.com/sampsyo
[mit]: https://opensource.org/licenses/MIT
