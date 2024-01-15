# Tesla Developer - FleetAPI for Powerwall

FleetAPI is a RESTful data and command service providing access to Tesla Powerwalls. Developers can interact with their own devices, or devices for which they have been granted access by a customer, through this API.

Note: the FleetAPI provides third party access to Tesla Vehicles as well as Energy Products.

## Requirements

* Tesla Partner Account - To be a developer, you will need to sign up as a Tesla Partner. This requires that you have a name (e.g. sole proprietor or business entity) and website.
* Web Site - You will need to own a domain name (website) and have control of that website.

## Setup

Step 1 - Sign in to Tesla Developer Portal and make an App Access Request: See [Tesla App Access Request](https://developer.tesla.com/request) - During this process, you will need to set up and remember the following account settings:

* DOMAIN - The domain name of a website your own and control.
* REDIRECT_URI - This is the URL that Tesla will direct users to after they authenticate. This landing URL (on your website) will extract the GET variable `code`, which is a one-time use code needed to generate the Bearer auth and Refresh token used to access your Tesla Powerwall energy devices.
* CLIENT_ID - This will be provided to you by Tesla when your request is approved.
* CLIENT_SECRET - Same as above.

Step 2 - Run the `create_pem_key.py` script and place the **public** key on your website at the URL: https://{DOMAIN}/.well-known/appspecific/com.tesla.3p.public-key.pem

Step 3 - Run the `setup.py` setup script. This will generate a partner token, register your partner account, generate a user token needed to access your Powerwall. It will also get the site_id and run a query to pull live power data for your Powerwall.

## References

* Developer Documentation about APIs - https://developer.tesla.com/docs/fleet-api#energy-endpoints

