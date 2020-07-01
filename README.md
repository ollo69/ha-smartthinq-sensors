[![](https://img.shields.io/github/release/ollo69/ha-smartthinq-washer/all.svg?style=for-the-badge)](https://github.com/ollo69/ha-smartthinq-sensors/releases)
[![hacs_badge](https://img.shields.io/badge/HACS-Default-orange.svg?style=for-the-badge)](https://github.com/custom-components/hacs)
[![](https://img.shields.io/github/license/ollo69/ha-smartthinq-washer?style=for-the-badge)](LICENSE)
[![](https://img.shields.io/badge/MAINTAINER-%40ollo69-red?style=for-the-badge)](https://github.com/ollo69)
[![](https://img.shields.io/badge/COMMUNITY-FORUM-success?style=for-the-badge)](https://community.home-assistant.io)

# LG ThinQ Devices integration for HomeAssistant
A Homeassistant custom component to monitor LG Washer, Dryer, DishWasher and Refrigerators using ThinQ API 
based on [WideQ project][wideq].<br/>

**Important Version note:** 
1. From version 0.3.x component name changed from `smartthinq_washer` to `smartthinq_sensors`
If you are upgrading to version 0.3.x from previous version, you must **remove component configuration and uninstall component**
from Home Assistant before upgrade.<br/>

2. From version 0.5.x devices state labels are loaded from "language pack" and shown in the language related to your account.
This change should solve all case of "unknown state" warning, due to the big change some sensors may not work as expected.
Please open an issue with all possible details to help me to fix possible new issues introduced.

**Important**: The component will **not work if you have logged into the ThinQ application and registered your devices using a social network account** (Google, Facebook or Amazon). In order to use the component you need to create a new independent LG account and make sure you log into the ThinQ app and associate your devices with it.
If during configuration you receive the message "No SmartThinQ devices found", probably your devices are still associated with the social network account. To solve the problem perform the following step:
- remove your devices from the ThinQ app
- logout from the app and login again with the independent LG account
- reconnect the devices in the app

**Note**: some device status may not be correctly detected, this depends on the model. I'm working to map all possible status developing the component in a way to allow to configure model option in the simplest possible way and provide update using Pull Requests. I will provide a guide on how update this information.<br/>

## Installation
You can install this component in two ways: via HACS or manually.

### Option A: Installing via HACS
If you have HACS, just go in the Integration Tab and search the "SmartThinQ LG Sensors" component to install it.

### Option B: Manually installation (custom_component)
1. Clone the git master branch.
2. Unzip/copy the smartthinq_sensors direcotry within the `custom_components` directory of your homeassistant installation.
The `custom_components` directory resides within your homeassistant configuration directory.
Usually, the configuration directory is within your home (`~/.homeassistant/`).
In other words, the configuration directory of homeassistant is where the configuration.yaml file is located.
After a correct installation, your configuration directory should look like the following.
    ```
    └── ...
    └── configuration.yaml
    └── secrects.yaml
    └── custom_components
        └── smartthinq_sensors
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
      region: my_smartthinq_region #(e.g. US)
      language: my_smartthinq_language #(e.g. en-US)
    ```

2. Reboot HomeAssistant

## Docs
In this example, "My [insert thing]" will just be the placeholder
#### Entities
| Entity ID | Entity Name | Description |
| :-- | :-: | :-- |
| sensor.my_washer | My Washer | Washer, turns On when on, turns Off when off |
| binary_sensor.my_washer_wash_completed | My Washer Wash Completed | Turns On when washer completed wash. You can use it in automations by triggering them when it goes from Off to On. |
| binary_sensor.my_washer_error_state | My Washer Error State | Off/OK means that it's fine. On/Error means there's an error. |
| sensor.my_dryer | My Dryer | Dryer, turns On when on, turns Off when off |
| binary_sensor.my_dryer_dry_completed | My Dryer Dry Completed | Turns On when dryer completed wash. You can use it in automations by triggering them when it goes from Off to On. |
| binary_sensor.my_dryer_error_state | My Dryer Error State | Off/OK means that it's fine. On/Error means there's an error. |

#### Attributes `sensor.my_washer`
Note: When something doesn't apply and/or is off, it may have a `-` as its value.
| Attribute ID | Description |
| :-- | :-- |
| model | Model ID of washer |
| mac_address | Mac address of washer |
| run_completed | Turns On when washer completed wash, just like binary_sensor.my_washer_wash_completed. |
| error_state | Off/OK means that it's fine. On/Error means there's an error, just like binary_sensor.my_washer_error_state. |
| error_message | When there is an error, this is what it is. ??? Unit please help |
| run_state | Current state of washer |
| pre_state | Previous state of washer |
| current_course | Current washing cycle |
| spin_option_state | Current spin mode |
| watertemp_option_state | Current option for water temperature |
| drylevel_option_state | ??? Please help |
| tubclean_count | ??? Please help |
| remain_time | How much more time is remaining ??? Unit please help |
| initial_time | ??? Please help |
| reserve_time | ??? Please help |

#### Examples (washer/dryer)
- Get a notification when the dry clothes are hot (automation)
```yaml
- id: 'dry_clothes_notification'
  alias: Dry clothes notification
  description: Alert when dryer finishes
  trigger:
  - entity_id: binary_sensor.my_dryer_dry_completed
    platform: state
    from: 'off'
    to: 'on'
  condition: []
  action:
  - data:
      title: 'The clothes are dry!'
      message: 'Get them while they're hot!'
    service: notify.notify
```
- Washer status card (LG전자 / CC BY (https://creativecommons.org/licenses/by/2.0) for image. Find the images [here](/washerpics/))
configuration.yaml:
```yaml
sensor:
  - platform: template
    sensors:
      washer_cycle_state:
        value_template: '{{state_attr(''sensor.my_washer'', ''remain_time'')}}'
        friendly_name: Washer Cycle State
        icon_template: 'mdi:washing-machine'
```
lovelace:
```yaml
cards:
  - type: conditional
    conditions:
      - entity: sensor.my_washer
        state: "on"
    card:
      aspect_ratio: '1'
      entity: sensor.washer_cycle_state
      image: /local/washerrunning.gif
      type: picture-entity
  - type: conditional
    conditions:
      - entity: sensor.my_washer
        not_state: "on"
    card:
      aspect_ratio: '1'
      entity: sensor.my_washer
      image: /local/washer.jpg
      type: picture-entity
type: vertical-stack
```
## Be nice!
If you like the component, why don't you support me by buying me a coffee?
It would certainly motivate me to further improve this work.

[![Buy me a coffee!](https://www.buymeacoffee.com/assets/img/custom_images/black_img.png)](https://www.buymeacoffee.com/ollo69)


Credits
-------

This component is developed by [Ollo69][ollo69] based on [WideQ API][wideq].<br/>
Original WideQ API was developed by [Adrian Sampson][adrian] under license [MIT][].

[ollo69]: https://github.com/ollo69
[wideq]: https://github.com/sampsyo/wideq
[adrian]: https://github.com/sampsyo
[mit]: https://opensource.org/licenses/MIT
