# ha-smartthinq-washer
Home Assistant custom integration for SmartThinQ LG washer devices

Note - Currently working with Home Assistant Core and potentially not working with Home Assistant (Hass.io). Home Assistant is returning "Invalid SmartThinQ credentials."

Install via HACS (https://hacs.xyz/):

Add cutsom repository -- 
HACS --> settings --> CUSTOM REPOSITORY:
ADD CUSTOM REPOSITORY of https://github.com/ollo69/ha-smartthinq-washer with a category of Integration,
Press the save icon

Install --
HACS --> INTEGRATIONS:
Search for "SmartThinQ LGE Washer",
Select install,
Reboot Home Assistant

Configure -- 
HA --> Supervisior --> Integrations --> add,
Search for "SmartThinQ LGE Washer",
Follow setup worflow

