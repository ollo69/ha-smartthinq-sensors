# LG ThinQ Devices integration for HomeAssistant

A HomeAssistant custom integration to monitor and control LG devices using ThinQ API based on [WideQ project][wideq].

Supported devices are:

- Air Conditioner
- Air Purifier
- Dehumidifier
- Dishwasher
- Dryer
- Fan
- Hood
- Microwave
- Range
- Refrigerator
- Styler
- Tower Washer-Dryer
- Washer
- Water Heater

**Important**: The component will **not work if you have logged into the ThinQ application and registered your devices using a social network account** (Google, Facebook or Amazon). In order to use the component you need to create a new independent LG account and make sure you log into the ThinQ app and associate your devices with it.
If during configuration you receive the message "No SmartThinQ devices found", probably your devices are still associated with the social network account. To solve the problem perform the following step:

- remove your devices from the ThinQ app
- logout from the app and login again with the independent LG account
- reconnect the devices in the app

**Important 2**: If you receive an "Invalid Credential" error during component configuration/startup, check in the LG mobile app if is requested to accept new Term Of Service.

**Note**: some device status may not be correctly detected, this depend on the model. I'm working to map all possible status developing the component in a way to allow to configure model option in the simplest possible way and provide update using Pull Requests. I will provide a guide on how update this information.

**Washer-Dryer remote start**: The component provides entities to select a course and override some of the course settings, before remotely starting the machine. The overrides available and their permitted values depend on the selected course. Attempts to set an invalid value for an override are ignored and result in an error message pop-up on the lovelace UI.  To remotely start the washer perform the following steps in order:

- Turn on the washer and enable remote start using its front panel.  This is an LG safety feature that is also required for the LG app.
- Select a course.
- Optionally, select a value for the course setting (e.g. water temperature) you would like to override.
- "Press" the Washer Remote Start button.

Nothing will happen/change on the washer and the component sensor entities will not show your selected course or overrides, until you press Remote Start.  This is the same behaviour as the LG app.

Please note, remote start feature override was developed for use in scripts and automations. If you use the locelace UI and select an invalid override value, it will incorrectly be shown as selected.  In fact, it has been ignored and you must refresh the page to see the currently selected value.  Pull requests that fix this issue are welcome. 

## Component configuration

Once the component has been installed, you need to configure it using the web interface in order to make it work.

1. Go to "Settings->Devices & Services".
2. Hit shift-reload in your browser (this is important!).
3. Click "+ Add Integration".
4. Search for "SmartThinQ LGE Sensors"
5. Select the integration and **Follow setup workflow**

**Important**: use your country and language code: SmartThinQ accounts are associated with a specific locale,
so be sure to use the country and language you originally created your account with.
Reference for valid code:

- Country code: [ISO 3166-1 alpha-2 code][ISO-3166-1-alpha-2]
- Language code: [ISO 639-1 code][ISO-639-1]

## Be kind

If you like the component, why don't you support me by buying me a coffee?
It would certainly motivate me to further improve this work.

[![Buy me a coffee!](https://www.buymeacoffee.com/assets/img/custom_images/black_img.png)](https://www.buymeacoffee.com/ollo69)

Credits

-------

This component is developed by [Ollo69][ollo69] based on [WideQ API][wideq].
Original WideQ API was developed by [Adrian Sampson][adrian] under license [MIT][].

[ollo69]: https://github.com/ollo69
[wideq]: https://github.com/sampsyo/wideq
[adrian]: https://github.com/sampsyo
[mit]: https://opensource.org/licenses/MIT
[ISO-3166-1-alpha-2]: https://en.wikipedia.org/wiki/ISO_3166-2
[ISO-639-1]: https://en.wikipedia.org/wiki/List_of_ISO_639-1_codes
