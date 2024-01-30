# LG ThinQ Devices integration for HomeAssistant

[![](https://img.shields.io/github/release/ollo69/ha-smartthinq-sensors/all.svg?style=for-the-badge)](https://github.com/ollo69/ha-smartthinq-sensors/releases)
[![hacs_badge](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![](https://img.shields.io/github/license/ollo69/ha-smartthinq-sensors?style=for-the-badge)](LICENSE)
[![](https://img.shields.io/badge/MAINTAINER-%40ollo69-red?style=for-the-badge)](https://github.com/ollo69)
[![](https://img.shields.io/badge/COMMUNITY-FORUM-success?style=for-the-badge)](https://community.home-assistant.io)

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

**Note**: some device status may not be correctly detected, this depends on the model. I'm working to map all possible status developing the component in a way to allow to configure model option in the simplest possible way and provide update using Pull Requests. I will provide a guide on how update this information.

## Installation

You can install this component in two ways: via [HACS](https://github.com/hacs/integration) or manually.

### Option A: Installing via HACS

If you have HACS, just go in the Integration Tab and search the "SmartThinQ LGE Sensors" component and install it.

### Option B: Manual installation (custom_component)

Prerequisite: SSH into your server.
[Home Assistant Add-on: SSH server](https://github.com/home-assistant/hassio-addons/tree/master/ssh)

1. Clone the git master branch.
`git clone https://github.com/ollo69/ha-smartthinq-sensors.git`
2. If missing, create a `custom_components` directory where your `configuration.yaml` file resides. This is usually in the config directory of homeassistant.
`mkdir ~/.homeassistant/custom_components`
3. Copy the `smartthinq_sensors` directory within the `custom_components` directory of your homeassistant installation from step 2.
`cp -R ha-smartthinq-sensors/custom_components/smartthinq_sensors/ ~/.homeassistant/custom_components`
4. (Optional) Delete the git repo.
`rm -Rf ha-smartthinq-sensors/`

    After a correct installation, your configuration directory should look like the following.

    ```shell
        └── ...
        └── configuration.yaml
        └── secrets.yaml
        └── custom_components
            └── smartthinq_sensors
                └── __init__.py
                └── config_flow.py
                └── const.py
                └── ...
    ```

5. Reboot HomeAssistant

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

## Docs

In this example, "My [insert thing]" will just be the placeholder

### Entities

| Entity ID | Entity Name | Description |
| :-- | :-: | :-- |
| sensor.my_washer | My Washer | Washer, turns On when on, turns Off when off |
| binary_sensor.my_washer_wash_completed | My Washer Wash Completed | Turns On when washer completed wash. You can use it in automations by triggering them when it goes from Off to On. |
| binary_sensor.my_washer_error_state | My Washer Error State | Off/OK means that it's fine. On/Error means there's an error. |
| sensor.my_dryer | My Dryer | Dryer, turns On when on, turns Off when off |
| binary_sensor.my_dryer_dry_completed | My Dryer Dry Completed | Turns On when dryer completed wash. You can use it in automations by triggering them when it goes from Off to On. |
| binary_sensor.my_dryer_error_state | My Dryer Error State | Off/OK means that it's fine. On/Error means there's an error. |

#### Attributes `sensor.my_washer`

Note: When something doesn't apply and/or is off, it may have a `-` as its value. Also, these are for @KTibow's washer, values may differ for yours. Feel free to open an issue/PR.
<details>
  <summary>
    Hidden, click to expand
  </summary>

| Attribute ID | Description |
| :-- | :-- |
| model | Model ID of washer |
| mac_address | Mac address of washer |
| run_completed | Turns On when washer completed wash, just like binary_sensor.my_washer_wash_completed. |
| error_state | Off/OK means that it's fine. On/Error means there's an error, just like binary_sensor.my_washer_error_state. |
| error_message | When there is an error, this is what it is. (Format unknown) |
| run_state | Current state of washer in words |
| pre_state | Previous state of washer in words |
| current_course | Current washing cycle in words |
| spin_speed | Current cycle's spin mode in words |
| water_temp | Current cycle's water temperature in words |
| dry_level | Unknown attribute, might be used in combined washers and dryers for the current cycle's dry level |
| tubclean_count | How many cycles have been ran without running the Tub Clean cycle |
| remain_time | How much more time is remaining, H:MM |
| initial_time | The orginal amount of time, H:MM |
| reserve_time | When in Delay Start mode, the delay amount, H:MM |
| door_lock | Whether washer door is locked, on/off |
| child_lock | Whether child lock is on, on/off |
| remote_start | Whether remote start is enabled, on/off |
| steam | Whether steam is enabled on supported washers, on/off |
| pre_wash | Whether using prewash cycle, on/off |
| turbo_wash | Whether Turbowash is enabled, on/off |

</details>

#### Attributes `sensor.my_dryer`

Note: When something doesn't apply and/or is off, it may have a `-` as its value. Also, these are for @KTibow's dryer, values may differ for yours. Feel free to open an issue/PR.
<details>
  <summary>
    Hidden, click to expand
  </summary>

| Attribute ID | Description |
| :-- | :-- |
| model | Model ID of dryer |
| mac_address | Mac address of dryer |
| run_completed | Turns On when dryer completed dry, just like binary_sensor.my_dryer_dry_completed. |
| error_state | Off/OK means that it's fine. On/Error means there's an error, just like binary_sensor.my_dryer_error_state. |
| error_message | When there is an error, this is what it is. (Format unknown) |
| run_state | Current state of dryer in words |
| pre_state | Previous state of dryer in words |
| current_course | Current drying cycle in words |
| temp_control | Current option for dryer temperature in words |
| dry_level | Current level for how much to dry |
| remain_time | How much more time is remaining, H:MM |
| initial_time | The orginal amount of time, H:MM |
| reserve_time | Unknown attribute, it could be this behaves the same as the washer's `reserve_time`, H:MM |
| child_lock | Child lock, on/off |

</details>

#### Examples (washer/dryer)

- Get a notification when the clothes are done drying (or when the clothes are done washing, automation)

```yaml
- id: 'dry_clothes_notification'
  alias: "Dry clothes notification"
  description: "Alert when dryer finishes"
  trigger:
  - entity_id: binary_sensor.my_dryer_dry_completed
    platform: state
    to: 'on'
  condition: []
  action:
  - data:
      title: "The clothes are dry!"
      message: "Get them while they're hot!"
    service: notify.notify
```

You can substitute "dry" and "dryer" for "wet" and "washer" if you want to use with a washer, for example.

- Timer Bar Card now supports this integration. If you like to show a progress bar for your washer/dryer go to https://github.com/rianadon/timer-bar-card and replace 'sensor.my_washer' with your sensor name.

![image](https://user-images.githubusercontent.com/117555636/210880751-604b6779-fd9d-4c23-b0d9-1a167f42a23a.png)
<details>
  <summary>
Code hidden, click to expand
  </summary>

```yaml
type: custom:timer-bar-card
entity: sensor.my_washer # replace with your entity name
duration:
  attribute: initial_time
invert: true # if you like to show the progress bar reverse like the screenshot above shows
bar_height: 11px # adjusts the height of the bar
text_width: 4em # adjusts the text width

```

</details>

- Custom card for dryer and washer

![image](https://user-images.githubusercontent.com/117555636/210881105-12a9f72f-b6f8-4f3a-bf00-1b73ba0af3b1.png)
<details>
  <summary>
Code hidden, click to expand
  </summary>

_Ensure that advance mode is enabled for your account else you won't see the resources page. **Your User** > **Advanced Mode**. Toggle to true._

Place this file in `/config/www/laundry.js`, and add a custom resource in **HA UI** > **Sidebar** > **Config** > **Dashboards** > **Resources** > **Plus** > **Add `/local/laundry.js`**.

In newer HA versions, you can find the custom resource page in **HA UI** > **Sidebar** > **Settings** > **Dashboards** > **[3-dots, top right]** > **Resources** **+ Add Resources** > **Add `/local/laundry.js`**

```js
class LaundryCard extends HTMLElement {
  // Whenever states are updated
  set hass(hass) {
    const entityId = this.config.entity;
    const state = hass.states[entityId];
    // Set data definitions
    const friendlyName = state.attributes["friendly_name"] || state.entity_id;
    const icon = state.attributes["icon"];
    if (!this.content) {
      this.innerHTML = `
        <ha-card header="${friendlyName}">
          <div class="main">
            <ha-icon icon="${icon}"></ha-icon>
            <span></span>
          </div>
        </ha-card>
      `;
      this.querySelector(".main").style.display = "grid";
      this.querySelector(".main").style.gridTemplateColumns = "33% 64%";
      this.querySelector("ha-icon").style.setProperty("--mdc-icon-size", "95%");
    }
    if (state.state == "on") {
      const totalTime = state.attributes["initial_time"];
      const remainTime = state.attributes["remain_time"];
      const totalMinutes = (parseInt(totalTime.split(":")[0]) * 60) + parseInt(totalTime.split(":")[1]);
      const remainMinutes = (parseInt(remainTime.split(":")[0]) * 60) + parseInt(remainTime.split(":")[1]);
      this.querySelector("ha-icon").style.color = "#FDD835";
      this.querySelector("span").innerHTML = `
${friendlyName} is running ${state.attributes["current_course"]}<br>
Currently ${state.attributes["run_state"]}<br>
${state.attributes["initial_time"]} total, ${state.attributes["remain_time"]} to go
<div class="progress-wrapper" style="height: 20px; width: 100%;">
  <div class="progress" style="display: inline-block; height: 20px;">
  </div>
  <span style="color: #FFFFFF; position: absolute; right: 33%;">50%</span>
</div>
`;
      this.querySelector(".progress-wrapper").style.backgroundColor = "#44739E";
      this.querySelector(".progress").style.backgroundColor = "#FDD835";
      this.querySelector(".progress").style.width = (totalMinutes - remainMinutes) / totalMinutes * 100 + "%";
      this.querySelector(".progress-wrapper span").innerHTML = Math.round((totalMinutes - remainMinutes) / totalMinutes * 100) + "%";
    } else {
      this.querySelector("ha-icon").style.color = "#44739E";
      this.querySelector("span").innerHTML = `${friendlyName} is off`;
    }
  }

  // On updated config
  setConfig(config) {
    const states = document.querySelector("home-assistant").hass.states;
    if (!config.entity || !states[config.entity] || !states[config.entity].state) {
      throw new Error("You need to define an valid entity (eg sensor.my_washing_machine)");
    }
    this.config = config;
  }

  // HA card size to distribute cards across columns, 50px
  getCardSize() {
    return 3;
  }

  // Return default config
  static getStubConfig() {
    for (var state of Object.values(document.querySelector("home-assistant").hass.states)) {
      if (state.attributes["run_state"] !== undefined) {
        return { entity: state.entity_id };
      }
    }
    return { entity: "sensor.my_washing_machine" };
  }
}

customElements.define('laundry-card', LaundryCard);
window.customCards.push(
  {
    type: "laundry-card",
    name: "Laundry Card",
    preview: true
  }
);
```

Lovelace:

```yaml
type: 'custom:laundry-card'
entity: 'sensor.the_dryer_dryer' # Washers work too!
```

</details>

- Mushroom-card

<img src="https://user-images.githubusercontent.com/10727862/174490941-c0148343-e31b-42fe-a856-376428ee53a5.png" width="500px"/>)

<details>
  <summary>
Code hidden, click to expand
  </summary>

**Note: You'll need to change the `sensor.dryer` to your own entity, and you might want to change `mdi:tumble-dryer` to `mdi:washing-machine` for washers.**

```yaml
type: custom:mushroom-template-card
primary: Dryer
secondary: >-
  {% if is_state("sensor.dryer", "on") %}

  Running {{ state_attr("sensor.dryer", "current_course") }}

  Currently {{ state_attr("sensor.dryer", "run_state") }}

  {{ state_attr("sensor.dryer", "initial_time") }} total, {{ state_attr("sensor.dryer", "remain_time") }} to go

  {% else %}

  Off

  {% endif %}
icon: mdi:tumble-dryer
entity: sensor.dryer
multiline_secondary: true
icon_color: '{{ "indigo" if is_state("sensor.dryer", "on") else "" }}'
tap_action:
  action: more-info
```

</details>

- Washer picture status card (LG전자 / CC BY (https://creativecommons.org/licenses/by/2.0) for image. Find the images [here](/washerpics/))

<details>
  <summary>
Code hidden, click to expand
  </summary>

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

</details>

## Obtaining API Information

For troubleshooting issues, or investigating potential new devices, information can be intercepted from the API via a man-in-the-middle (MITM) http proxy interception method. Charles, mitmproxy, and Fiddler are examples of software that can be used to perform this mitm 'attack'/observation.

This can be done using a physical or virtual device that can run the LG ThinQ app. While it is theoretically possible with iOS, it is much easier to do this using Android.

Windows 11 enables the ability to run Android apps on most modern machines, making this process more accessible by eliminating the need for a physical device or separate emulation/virtualization software.

For information on how to do this with Windows Subsystem for Android (WSA) on Windows 11 using mitmproxy, please see the repo [zimmra/frida-rootbypass-and-sslunpinning-lg-thinq](https://github.com/zimmra/frida-rootbypass-and-sslunpinning-lg-thinq) (Method tested August '23, LG ThinQ Version 4.1.46041)

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
