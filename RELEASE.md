# RELEASE NOTES

## Unreleased

* fix(connect): a reconnect that fails in every mode now keeps the client it had, along with the mode and TEDAPI state it already restored. Before, the last fallback attempt was left behind, usually an unauthenticated cloud client, so a local-only install raised `PyPowerwallCloudTeslaNotConnected` on every call until the gateway came back, even though it never uses cloud. Calls during an outage now fail the same way as before it started. The first connect is unchanged. (#454)

## v0.23.0 - Proxy HTTPS Certificates and Dispatch Warranty Warning

* fix(proxy): `PW_HTTPS=yes` starts again in Docker (images since v0.15.0 left out the bundled `localhost.pem`), with an HTTPS-aware health check. New `PW_HTTPS_CERT` / `PW_HTTPS_KEY` use your own certificate, as in pypowerwall-server; the shared bundled certificate stays the default and now logs a warning. Proxy t110. (#449)
* docs(v1r): battery dispatch now **boldly warns that it could void or limit your Tesla Powerwall warranty**. The Powerwall warranty quoted in #450 gives unlimited cycles only for solar self-consumption, time-based control and backup; any other use is limited to 37.8 MWh of total energy throughput. Added to the README and API.md warnings, the `dispatch_battery_power()` docstrings and the WARNING logged for each accepted dispatch. Thanks @longzheng for spotting this and @BJReplay for working out what the limit means in daily use. (#451, #450)
* Library version bumped to `0.23.0`

## v0.22.2 - Battery Dispatch: Use at Your Own Risk

* docs(v1r): battery dispatch is now clearly marked **use at your own risk** in README, API.md and the `dispatch_battery_power()` docstrings. A dispatch takes direct control of the battery through an undocumented Tesla command and overrides the backup reserve and grid export settings, and we don't know whether incorrect use could damage a home, a Powerwall system or the grid. The docstring no longer says it "does not change backup reserve" without saying the reserve is ignored while a dispatch runs. Each accepted dispatch is now logged at WARNING (action, watts, duration). Paired with pypowerwall-server's `PW_BATTERY_DISPATCH` opt-in (jasonacox/pypowerwall-server#185). (#446)
* Library version bumped to `0.22.2`

## v0.22.1 - Signed Wi-Fi v1r Native Reads

* fix(tedapi): with `wifi_v1r_fallback=True` and the LAN failover tripped, native `/api/*` reads (`get_native_api()`, used for `/api/meters/aggregates`) now go through the selected signed transport's `api_get()` instead of the customer-session WiFi/LAN host loop, so a failed WiFi read no longer retries the dead LAN. A failed read returns `None`. Flag-off and LAN-healthy reads are unchanged. Hardware-validated read-only on a Powerwall 3 (v1r LAN + Wi-Fi, failover simulated with the LAN up): one login and one GET to the Wi-Fi host, none to the LAN, and the same gateway DIN on both routes; with the Wi-Fi host unreachable the read returned `None` without touching the LAN.
* Library version bumped to `0.22.1`

## v0.22.0 - Local Battery Dispatch, Signed Wi-Fi v1r Failover, Instantaneous Power Limits and FleetAPI 429 Fix

* feat(v1r): local timed battery dispatch. `Powerwall.dispatch_battery_power(power_watts, duration_seconds)` sets battery power for 1-86400 seconds (positive watts discharge, negative charge) and `resume_battery_operation()` releases it early; the gateway returns to its configured mode when the duration ends. Both use the signed v1r transport (TEG fields 37/38) and write no gateway configuration. Inputs are validated before any I/O, a result is returned only with the gateway's matching acknowledgement, rejections are logged with their status code, and the battery-power samples (`status`, `controller`, PW3 vitals) are cleared after an accepted command. **A dispatch overrides the backup reserve and the export setting:** on a Powerwall 2 (Backup Gateway 1, firmware 26.34.0) a discharge with the reserve at 100% and export set to `pv_only`/`never` still ran, exported the excess and raised `BackfeedLimited`/`BatteryUnexpectedPower` alerts. Validated on Powerwall 3 over v1r LAN, on one unit (firmware 26.26.4) and on 2x Powerwall 3 (firmware 26.26.11): discharge, `0` W, resume, expiry, the 10,000 W discharge limit (status code 11), and charging from the grid with grid charging enabled (−1000 W). Thanks @longzheng, tested by @BJReplay and @jasonacox-sam; protobuf schema documented by [Teslemetry/tesla-protocol](https://github.com/Teslemetry/tesla-protocol) (#440, #437).
* feat(tedapi): Powerwall 2 instantaneous battery power limits. `/api/system_status` `instantaneous_max_charge_power` / `instantaneous_max_discharge_power` (hard-coded `0`) are now the sums of the msa `TEPOD` components' `POD_available_charge_power` / `POD_available_dischg_power`, matching the local API, and the `TEPOD--` vitals blocks carry the same two values. The V2024_06 device-controller request appends `TEPOD` to its unsigned `msaComp` type list (new `EXTRA_COMPONENT_TYPES`; the capture and its signature are unchanged). A sum is reported only when every POD component gives a usable value; otherwise, and under V2026_06, the fields stay `0`. Validated on 2x Powerwall 2 (firmware 26.34.1): 14000/15570 W, equal to the local API in the same read. On 2x Powerwall 3 (firmware 26.26.11, Wi-Fi TEDAPI and v1r) nothing changes: the fields stay `0` and vitals, temps and fans are identical. Thanks @erikgieseler, PW3 check by @jasonacox-sam (#429).
* feat(v1r): opt-in signed Wi-Fi v1r failover. With `Powerwall(..., wifi_v1r_fallback=True)` and a `wifi_host`, the leader gets a second signed `TEDAPIv1r` transport on the gateway's Wi-Fi; once the v1r LAN failover trips, every leader v1r read and write (config, max backup, backup events, islanding, battery dispatch) uses it and never falls back to legacy Wi-Fi TEDAPI. A failed read returns `None`; writes are gated by a read-only `wifi_v1r_ready()` probe and never dispatched when it fails, and a dispatched attempt is final. Default `False` leaves existing behavior unchanged; followers keep the Wi-Fi TEDAPI session. Validated on a Powerwall 2 (firmware 26.34.1) over an ESP32 bridge: failover, live 401 re-login, and reserve writes with readback; a read-only cold-failover check passed on 2x Powerwall 3. Max backup and islanding over Wi-Fi were not exercised on hardware. Thanks @erikgieseler, PW3 check by @jasonacox-sam (#441).
* feat(fleetapi): new `PW_FLEETAPI_HTTP=1.1` setting forces HTTP/1.1 for all FleetAPI requests, an escape hatch for intermittent HTTP/2 connection-reuse errors (`COMPRESSION_ERROR`, h2 state errors). Reported in the proxy's `/stats` `config` (proxy t109) (#436).
* fix(fleetapi): request storms and 429 cascades in FleetAPI mode. When the cache expired, every proxy poller thread sent its own identical request (1,332 HTTP 429s vs 547 HTTP 200s in a 10-minute EU-site log). Now:
  * concurrent identical GETs share one in-flight request;
  * Tesla's retry guidance (`Retry-After` seconds or HTTP-date, or "Retry in N seconds" in the body) opens one shared backoff window, during which cache-missing reads return `None` immediately - nothing ever sleeps in the library;
  * forced reads (re-reads after a write) always send their own request;
  * cache expiry is jittered so endpoints don't all expire together.
  
  The reporter's 10-minute run showed zero 429s at default settings. Thanks @jasonacox-sam, reported and field-tested by @VivLloyd (#436, #433).
* fix(proxy): `/stats`, `/help` and the power-flow page no longer show the account email, Tesla site ID or file paths (shipped in proxy t108) (#431).
* docs(v1r): README and API.md warn that a battery dispatch overrides the backup reserve and the export setting, from @BJReplay's Powerwall 2 run, and record the Powerwall 3 results (#440, #442).
* tests: new `test_v1r_dispatch.py` (wire format, validation, acknowledgement, cache) and `test_fleetapi_thundering_herd.py` (coalescing, backoff, cache recheck, follower deadline, forced reads); `test_v1r_wifi_fallback.py` covers the signed Wi-Fi routing, the write gate and LAN recovery mid-call; `test_pw2_msa_signals.py` and `test_tedapi_regressions.py` cover the TEPOD request and the instantaneous sums (#440, #441, #436, #429).
* ci: checks work on GitHub's Ubuntu 26.04 runners. The Python 3.9 jobs run on `ubuntu-24.04` (3.9 has no 26.04 build; `requires-python >= 3.9` is unchanged), the simulator readiness check reads the HTTP status, the simulator (v0.2.6) sends TLS close_notify, and `jasonacox/pwsimulator:latest` is published only from `main` (#435).
* Library version bumped to `0.22.0`

## v0.21.0 - Powerwall 2 Per-Unit Vitals, Battery Power Limits, PW_FAILOVER and TEDAPI Recovery Fix

* feat(tedapi): Powerwall 2 per-Powerwall vitals from the DeviceController msa components. The V2024_06 `device_controller_full` request now appends 14 more signal names to its unsigned `msaSignals` variable, after #419's `SYNC_Uptime` (`PW2_MSA_SIGNAL_NAMES`, via `EXTRA_SIGNAL_NAMES`; the capture, its signature and its `msaComp` component types are unchanged). They fill PW2 vitals keys that mirror the original `/api/devices/vitals` and were hard-coded `None`:
  * on each `TEPINV` block: `PINV_EnergyCharged` and `PINV_EnergyDischarged` (lifetime Wh), `PINV_HardwareEnableLine`, `PINV_PllFrequency`, `PINV_PllLocked`, `PINV_PowerLimiter`, `PINV_Qout` and `PINV_ReadyForGridForming`
  * `THC_State` on each `TETHC` block
  * `SYNC_ExternallyPowered` and `SYNC_SiteSwitchEnabled` on `TESYNC`

  Three new keys join each `TEPINV` block: `PINV_HeatsinkTemp`, `PINV_LifetimeEnergyCharged` and `PINV_LifetimeEnergyDischarged`. Values pass through as the gateway delivers them, `None` included. The `boolValue`/`textValue` fields are read as well as `value`, so a `False` or an enum is not lost.
  * The `TETHC` and `TESYNC` values join on serial.
  * The `TEPINV` values come from the msa component of the battery *module*, whose serial is not the package serial the block is named by. Nothing in the payload links the two, so `_pw2_msa_module_pairing()` pairs each package's TETHC with the TEPINV that follows it. Serial-less slots are skipped, even ones carrying a live signal. If the layout is irregular in any way, every module value stays `None` rather than risk giving one Powerwall another's counters.
  * Hardware-validated on 4x Powerwall 2 behind a Backup Gateway 1 (firmware 26.34.0, v1r LAN), and with this request on a second Backup Gateway 1 site with 4x Powerwall 2 (firmware 26.18.3, one warranty-replacement unit with different part numbers). The module counters' sum matched the Fleet API cumulative battery discharge to 0.12%. Over 5.9 hours of charging, the charged counters' rise matched the gateway's own battery meter, integrated, to 0.07%. The component order was identical in every read over 46 hours, and again after a gateway restart (no firmware change).
  * `temps()`, `/temps`, `msaComp` and every existing key are unchanged. `SYNC_ExternallyPowered` / `SYNC_SiteSwitchEnabled` also fill on Powerwall 3 sites that report a SYNC device (`esCan.bus.SYNC` with a serial, e.g. behind a Backup Gateway 2): they were `None` there and now carry the gateway's value (`False` on 2x PW3, firmware 26.26.11, over WiFi TEDAPI and v1r), matching the original `/api/devices/vitals`. Nothing else in Powerwall 3 vitals changes: the other 12 names come back `null` on PW3 and are not read there (hardware-checked by @jasonacox). The `TEPOD` `POD_*` placeholders stay `None`, because they need TEPOD in `msaComp`. Under V2026_06 the signed DeviceControllerQuery can't carry extras, so these keys stay `None` there. Thanks @jcl-bit (#416, #409).
* feat(tedapi): `/api/system_status` `max_charge_power`, `max_discharge_power` and `max_apparent_power` are filled (they were always `null`) the way the gateway's local API reports them: the site's nominal system power from the gateway config (`site_info.nominal_system_power_ac`, in kW, converted to W), capped at the inverters' usable power where the inverters report it. A site whose wiring derates its Powerwalls below nameplate reports the derated value, as its local API does (2x Powerwall 2 at 4600 W each on single-phase wiring: 9200, not the 10000 nameplate). Powerwall 3 reports the nameplate, since it has no per-inverter values here. Cloud and FleetAPI report the nameplate. Thanks @erikgieseler (#423).
* feat(tedapi): `/api/system_status` `inverter_nominal_usable_power` is filled (it was hard-coded `0`) with the sum of the active inverters' `esCan.bus.PINV[].PINV_PowerCapability.PINV_Pnom`, matching the local API. It stays `0` when no inverter reports one (Powerwall 3) (#423).
* feat(proxy): new `PW_FAILOVER` setting (default `yes`) exposes the library's `failover` option (#395) in the proxy. Set `PW_FAILOVER=no` to pin the configured transports: the v1r leader stays on the wired LAN instead of switching to `PW_WIFI_HOST`, a failed request returns no data instead of being rerouted, and the proxy never falls back from local to FleetAPI or Cloud mode (at startup it retries the configured mode until it connects). Only `no` turns it off. `/stats` reports it under `config`, and `/health` shows `failover` per transport. Requested by @BJReplay (#427, #402).
* fix: TEDAPI recovery no longer gets stuck on Tesla cloud after a gateway outage. With failover on (the default) and cloud credentials available, the proxy's recovery `connect()` could succeed by falling back to cloud. The proxy counted that as recovered (cloud answers `version()` too), then stopped probing because `pw.tedapi` was off, and stayed on cloud with no TEDAPI data until restart. Now `Powerwall.connect()` always starts from the mode set at construction, as its docstring says, instead of where an earlier failover left it, and a successful cloud or FleetAPI connect clears any TEDAPI state left from an earlier failover to local. The proxy counts recovery only when the connection is back in TEDAPI mode, and treats a connection that has left TEDAPI mode as a failed probe. Cloud data keeps flowing while recovery runs. (#425, #424)
* docs: README, proxy README and AGENTS.md say which TEDAPI query set to use. Keep the default `V2024_06` unless you need bearer mode: both sets are pre-signed query payloads, but only `V2024_06` takes its signal names as unsigned variables, so it is the only set pypowerwall can extend, and PW3 temperatures, fans and battery health and the gateway uptime are `null` under `V2026_06`. `V2026_06` stays for bearer mode on solar-only gateways. The docs now describe `V2026_06` as a pre-signed query set rather than a Tesla-signed or Tesla-provided one. (#422)
* docs: README v1r key registration covers the Powerwall 2 physical proof (one unit's On/Off switch off for about 15 seconds). (#416)
* tests: new `test_pw2_msa_signals.py`, with a redacted raw PW2 device-controller response (`tests/tedapi/fixtures/pw2_device_controller_full.json`, made with this request). It covers the request (signature and `msaComp` unchanged, names appended), value fields, the pairing rule and its failure cases, the vitals fills, ambiguous pairing, and that every other vitals key is unchanged. `test_pw3_fans.py` and `test_pw3_temperatures.py` no longer assume the device-controller request is the untouched capture object. (#416)
* Library version bumped to `0.21.0`

## v0.20.0 - PW3 Battery Health, Truthful Gateway Status and Site Info, Token Hygiene

* feat(tedapi): Powerwall 3 battery health and inverter detail in vitals. Tesla's own app queries (the V2026_06 `PW3Query` and `ComplianceQuery`) request 23 PW3 signals our default V2024_06 query didn't; they are now requested as ComponentsQuery extras (`PW3_APP_SIGNAL_NAMES`) and passed through as delivered. Each battery's `TEPOD` block gains `BMS_kwhDischargeTotal` (lifetime kWh discharged), `BMS_LOG_ahDischargeTotal`, `BMS_LOG_cacAvg`, `BMS_LOG_numFullBattCycles`, `BMS_LOG_overDischargeCounter`, `BMS_LOG_selfDischargeRate`, `HVP_SafetyBiDisconnectState` and `HVP_a061_LockoutOnIsoFaultRetry`. Each Powerwall's `TEPINV` block gains `PCH_AcRealPowerSum`, `PCH_AcVoltageLL`/`CN`, the rapid-shutdown and external-switch states (`PWS_*`), and the battery aggregate's expected energy (`BAGGR_*`). Enum and boolean signals now come through (they arrive in `textValue`/`boolValue`). Empty expansion slots report placeholder values and are still skipped. Validated live on 2x PW3 (firmware 26.26.11): only keys added. Under V2026_06 the `PCH`/`PWS`/`BAGGR`/`HVP` signals also arrive (Tesla's `PW3Query` requests them); the `BMS_*` ones are V2024_06 only.
* fix(tedapi): `/api/site_info` returned `null` for every field. It read config.json's top level, but these keys live under its `site_info` section. Site name, timezone, system energy/power, meter limits, panel current and grid code (with country, state and utility) are now filled, in the gateway's shape; `grid_voltage_setting`/`grid_freq_setting`/`grid_phase_setting` stay `null` because config.json has no such settings. Validated live on 2x Powerwall 3. (#420)
* docs: removed an incorrect firmware version (26.34.0) from two code comments, and corrected it to 26.26.11 in the v0.19.0 release notes.
* tests: new `test_tedapi_site_info.py`.
* fix: `/api/status` `start_time` and `up_time_seconds` now mean what they mean on a gateway (when it last started), or `null` where that isn't known. Before, every non-local backend put an install/commission date in `start_time` and `null` uptime, and cloud/FleetAPI reported a hard-coded `git_hash` and `sync_type: "v2.1"`. Strict clients failed to parse the dates: evcc's go-powerwall reads `start_time` as `2006-01-02 15:04:05 -0700` and `up_time_seconds` as a Go duration (#418). (#419)
  * TEDAPI: computed from `SYNC_Uptime`, the Backup Gateway sync board's uptime in ms, which is now requested through the device-controller query's unsigned `msaSignals` (`EXTRA_SIGNAL_NAMES`), in the gateway's formats (`2026-09-24 21:28:16 -0700`, `399h42m6.976s`). `start_time` stays fixed for a boot, changing only when the counter resets, because the computed start wobbles by 1-2 s and drifts slowly against the gateway clock. `null` on sites without a sync board and under V2026_06. New `TEDAPI.get_gateway_uptime()`; vitals gain `SYNC_Uptime` on `TESYNC`. `git_hash` is filled from the firmware. Validated on 2x PW3 + Backup Gateway 2 over WiFi and v1r: the start matched the 2026-09-24 firmware-update reboot within a minute, and go-powerwall parses the output.
  * Cloud and FleetAPI: the Tesla site API has no start time, uptime, git hash or sync type, so these are `null` (`sync_type` `"unknown"`).
  * The dates aren't lost: TEDAPI adds `battery_commission_date`, cloud/FleetAPI add `installation_date`, each passed through unchanged.
  * **Compatibility:** same keys and failure shape, plus the date key. `start_time` changes value, and is `null` without a source. `pw.uptime()` returns the uptime where it was `None`. Nothing in pypowerwall, the proxy, pypowerwall-server or Powerwall-Dashboard parses these fields.
* docs: API.md describes the `/api/status` time fields. AGENTS.md covers `msaSignals` extras and discovering signal names safely.
* tests: new `test_gateway_uptime.py`; `test_pw3_fans.py`/`test_pw3_temperatures.py` no longer assume the device-controller request is the untouched capture.
* fix: `strings()` no longer modifies the dict returned by `vitals()`. It copied each PVS block's string keys (`PVS_StringA_Connected` ... `PVS_StringF_Connected`) into the matching `PVAC--` block of that dict. On a Powerwall 3 (TEDAPI full or v1r), `vitals()` merges the PVAC/PVS blocks in by reference from the `pw3_vitals` cache, so the copied keys stayed in the cache. Every `vitals()` call before the cache expired (`pwcacheexpire`, 5 s by default), including the proxy's `/vitals`, then showed them on the PVAC blocks, but only if `/strings` had run first. A long-running proxy polled by Powerwall-Dashboard showed them almost all the time, and a freshly started one didn't. `strings()` now merges the PVS keys into a copy of each PVAC block. Other backends build a new `vitals()` dict on every call, so they were never affected. (#414)
  * **Compatibility:** `strings()` / `/strings` output is unchanged, including key order. On Powerwall 3, `/vitals` `PVAC--` blocks no longer carry `PVS_String*_Connected`. Those keys were never part of the gateway's PVAC data: the local PW2/PW+ `/api/devices/vitals` snapshots in `docs/vitals-example*.json` carry them only in the `PVS--` block. The copy has been in `strings()` since v0.1.0, but `vitals()` used to build a new dict on every call, so it never reached `/vitals` until the PW3 cache. The keys remain in the `PVS--` blocks and `/strings`. Nothing reads them from PVAC blocks: Powerwall-Dashboard's telegraf doesn't poll `/vitals`, and pypowerwall-server builds `/pw/strings` from the `PVS--` blocks itself. Maintainer decision (@jasonacox, 2026-10-10): ship the fix and drop the keys rather than adding them to every `/vitals` response.
* docs: API.md, proxy/API.md and docs/reference/devices.md now say where solar string data lives in vitals: measurements on the `PVAC--` block, `PVS_String*_Connected` on the `PVS--` block. They also say that `strings()` / `/strings` combine the two without modifying `vitals()`.
* tests: new `test_strings_vitals_isolation.py`. `vitals()` is the same before and after `strings()`, both for a backend that returns one cached dict and through the real TEDAPI Powerwall 3 cache path. The `strings()` output, simplified and verbose, is pinned byte-for-byte to its pre-fix value.
* fix(auth): interactive Tesla login no longer prints the refresh/access tokens to the console. Both login backends (macOS WKWebView and the pywebview flow used on Windows/Linux) printed the full RT/AT unconditionally after the token exchange; now tokens are printed only by `authtoken` (where copying them is the point). The `setup` path prints only a non-secret confirmation. `v1r_register`'s code exchange no longer prints the first 30 characters of either Fleet API token — just the expiry and the file it saved to. The pywebview backend also now returns the populated `token_data` dict instead of `{}`, the empty-token-dict behavior reported on Windows (#409). (#415)
* fix(fleetapi): `setup -fleetapi` no longer prints Fleet API tokens either. Step 3A printed a 40-character prefix of the partner token and step 3D printed the full access and refresh tokens after the code exchange; nobody copies these — setup saves them to the Fleet API config file (created with owner-only permissions). Both now print non-secret confirmations (`Partner token obtained`, `Tokens generated and saved to <config file>`). (#415)
* Library version bumped to `0.20.0` (minor bump: new PW3 vitals signals, new `/api/status` keys `battery_commission_date`/`installation_date`, new `SYNC_Uptime` vitals key, new `TEDAPI.get_gateway_uptime()`)

## v0.19.0 - Home Assistant Protobuf Compatibility, Wi-Fi Remote Meters, and CLI Temps/Fans

* fix: `get_reserve()` returns `None` instead of raising `TypeError: float() argument must be a string or a real number, not 'NoneType'` when `/api/operation` reports `backup_reserve_percent` as `None`. The TEDAPI client builds that response from `site_info.backup_reserve_percent`, which a solar-only gateway (no battery) doesn't have, so `python -m pypowerwall get` crashed on those systems.
* fix(tedapi): `extract_fan_speeds()` / `get_fan_speeds()` now also read the PVAC fan RPMs from `esCan.bus.PVAC[].PVAC_Logging`, which is where the Tesla-signed V2026_06 DeviceControllerQuery requests them — its TEMSA `signals` filter no longer names `PVAC_Fan_Speed_*`, so reading only `components.msa[].signals[]` returned nothing (empty `/fans` in the proxy and pypowerwall-server) on that query set. The `msa` path is kept for V2024_06; both are merged, a device reported in both keeps the `PVAC_Logging` values, and entries flagged `isMIA` or without a `packageSerialNumber` are skipped (a PW3 reports 8 such empty slots with fan RPMs 0, which would otherwise show up as a phantom `PVAC--None--None` fan). `vitals()` no longer raises `KeyError` when a PVAC reports only one of the two RPMs (the missing one is `None`), which the new fan data would otherwise have exposed under V2026_06. Output shape (`PVAC--{part}--{serial}` → `{PVAC_Fan_Speed_Actual_RPM, PVAC_Fan_Speed_Target_RPM}`) is unchanged.
* feat(cli): `python -m pypowerwall get` now includes per-device temperatures (`pw.temps()`) and fan speeds (`get_fan_speeds()`) when the connection mode reports them, in the same shapes as the proxy's `/temps` and `/fans`: nested `temps`/`fans` objects in `-format json`, one row per device in text, and `temps.<device>` / `fans.<device>.<signal>` columns in `-format csv`. Cloud and Fleet API output is unchanged (no keys or columns added when there's no data). `get` and `set` also take `-tedapi_api_version` (`V2024_06`/`V2026_06`, with `-tedapi` or `-v1r`) and `-tedapi_auth_mode` (`basic`/`bearer`, with `-tedapi`), the CLI equivalents of `PW_TEDAPI_API_VERSION` / `PW_TEDAPI_AUTH_MODE`; unset, the library defaults apply as before, and either one with a mode it doesn't apply to is an error rather than silently ignored.
* tests: new `test_tedapi_fan_speeds.py` (msa-only, PVAC_Logging-only, merged precedence, MIA/None/malformed payloads, PW3 empty slots, `get_fan_speeds()` delegation, `vitals()` PVAC fan fields incl. a missing RPM); new `test_cli_get.py` (`get` temps/fans in json, text and csv; unchanged output without them; the TEDAPI options reach `Powerwall()` and are rejected where they'd be ignored)
* fix(tedapi): `vitals()` and `/api/meters/aggregates` no longer raise when the gateway returns config with `meters: null` or `vin: null` - seen from a gateway restarted mid re-commissioning. Two separate paths: a null or non-list `meters` (or a null config) breaks both `vitals()` and `/api/meters/aggregates` via `derive_meter_config()`, which now treats it as "no meters" instead of iterating `None`, and skips null entries inside the list; a null `vin` breaks `vitals()` only, where the gateway `STSTSM--` block is built - it now degrades to `partNumber`/`serialNumber` `None` instead of raising `AttributeError` on `.split('--')`. `/api/meters/aggregates` never parses the VIN. Fixes #407
* fix(protobuf): pypowerwall can now be loaded in the same Python process as other libraries that compile Tesla's protobufs, e.g. Home Assistant 2026.10's Teslemetry integration (`aiopowerwall`), `tesla-protocol`, or `googleapis-common-protos`. Python keeps one protobuf descriptor pool per process, and pypowerwall registered generic names in it (`tedapi.proto` / package `tedapi`, `tesla.proto` / package `teslapower`, and, for the opt-in V2026_06 set, `google.rpc.Status` and Tesla's `tesla.proto.*` packages), so whichever library imported second failed with `TypeError: Couldn't build proto file into descriptor pool: duplicate file name tedapi.proto` (or `duplicate symbol ...`). Every generated module now registers under its own import path, e.g. file `pypowerwall/tedapi/protobuf/V2024_06/tedapi.proto`, package `pypowerwall.tedapi.protobuf.V2024_06.tedapi`. `tools/gen_proto.sh` stages renamed copies via the new `tools/namespace_protos.py`; the checked-in `.proto` sources are unchanged. (#408)
  * **Compatibility:** no change to the Python API, the wire format, or proxy output. Module paths, message classes (`tedapi_pb2.Message`, ...), fields, enums and serialized bytes are identical; the 312 messages and 58 enums were compared structurally, and responses were A/B-checked live on two Powerwall 3s (WiFi and v1r, `V2024_06` and `V2026_06`). **What does change** is the protobuf *descriptor metadata*: `Message.DESCRIPTOR.full_name` (`tedapi.Message` → `pypowerwall.tedapi.protobuf.V2024_06.tedapi.Message`), `DESCRIPTOR.file.name`/`package`, and therefore lookups by name in the default pool (`descriptor_pool.Default().FindMessageTypeByName('tedapi.Message')`) and any `google.protobuf.Any` type URL built from our messages. Code that only constructs, serializes and parses messages is unaffected. The V2026_06 modules now use absolute imports (`from pypowerwall.tedapi.protobuf.V2026_06 import ...`), and protoc's private module aliases inside the generated files were renamed.
* fix(tedapi): `tedapi_api_version="V2026_06"` no longer reports every import failure as "requires protobuf>=6.33.6". That advice is now given only when the installed protobuf is older than 6.33.6; any other failure (such as a descriptor-pool clash) is reported with its real cause. (#408)
* tests: new `test_protobuf_namespace.py` (every generated module registers under its import path; pypowerwall loads after bare-named `tedapi.proto`/`teslapower`/`google.rpc.Status`/`tesla.proto.*` copies are registered; the V2026_06 import error names its real cause). Two V2026_06 tests in `test_pw3_fans.py` now skip on the protobuf 4.25.1 floor like the others. `check-protobuf.yml` also runs when `gen_proto.sh` or `namespace_protos.py` change.
* fix(tedapi): recognise the Wi-Fi Tesla Remote Meter. Remote-meter support (#386) matched only config.json meter type `trm_mb`, but a Wi-Fi-connected Tesla Remote Meter is declared as `trm_wifi` and reports through the same `teslaRemoteMeter` field with the same reading shape. On a `trm_wifi` site `get_remote_meter_readings()` therefore returned `{}` without fetching, the `/api/meters/aggregates` solar (and site) Remote Meter fallback never ran, and `vitals()` built the `TRM--<din>` block with no meter config: `Location` `None` and `real_power_scale_factor` not applied (CT0 `InstRealPower` 1517 W on a meter with factor 2, while the gateway's own SOLAR aggregate read 3096 W). New module constant `REMOTE_METER_TYPES = ("trm_mb", "trm_wifi")` in `pypowerwall/tedapi/__init__.py` is used by `get_remote_meter_readings()` and `vitals()`, so `trm_wifi` sites now get the scaled, located `TRM--<din>` block and the per-phase solar current/voltage fallback exactly as `trm_mb` sites already did. `derive_meter_config()`'s default (`neurio_w2_tcp`) is unchanged, and `trm_mb` output is unchanged. Remote-meter hierarchy entries (from `get_remote_meter_readings()` / `aggregate_remote_meter_data()`) gain a `Timestamp` key carrying the meter's own reading time; the flat `TRM_CT*_` vitals keys are unchanged (the block already has `lastCommunicationTime`). (#400)
* feat(tedapi): hold solar through `SolarMeterComms` dropouts in `/api/meters/aggregates`. Roughly every 5 minutes the gateway misses a `trm_wifi` meter's Wi-Fi packet for 8-28 s. In those samples the gateway reports SOLAR `realPowerW` 0 and subtracts the missing solar from LOAD, which goes negative (e.g. SOLAR 2852.6 -> 0, LOAD 1194.1 -> -1752.0, SITE unchanged); `control.alerts.active` gains `SolarMeterComms`; and `teslaRemoteMeter` keeps the last good reading with its timestamp frozen a few seconds behind the gateway clock. The alert clears in the same sample the reading resumes. `current_power()` relays meterAggregates verbatim, so consumers saw solar drop to zero and load go negative several times an hour. Now, when the alert is active and the gateway's solar is None or at most `SOLAR_METER_HOLD_ZERO_W` (10 W; the "missing" value is usually exactly 0 but has been observed as 1 W), the aggregates solar section is held at the retained remote-meter reading (sum of solar-located CTs, already scaled) and the missing amount is added back to load, with solar/load current recomputed from the corrected power and `; solar held from remote meter reading during SolarMeterComms (age Ns)` appended to the solar `disclaimer`. The hold applies only if the retained reading is at most 60 seconds (module constant `SOLAR_METER_HOLD_MAX_AGE` in `pypowerwall/tedapi/pypowerwall_tedapi.py`) older than the gateway's system time - or up to that many seconds newer, since the Full query is fetched just after the status and the meter's first packet after a dropout can be stamped a second later than the status snapshot; a stale or undatable reading, no solar remote CT, or a retained value of 0 leaves the gateway's values exactly as reported. Sites without a remote meter, without the alert, or with non-zero solar are untouched, and an error in the correction leaves the aggregates as they were. `current_power()`, `vitals()` and the other endpoints still report the gateway's raw values. (#400)
* fix(tedapi): `/api/meters/aggregates` no longer raises when a power value is `None` while its voltage source still reports. Each section divided power by voltage guarding only the voltage, so a location missing from meterAggregates - or `control: null`, as when the gateway's site manager isn't running - raised `TypeError` instead of degrading. That included missing solar on any remote-meter site, where the meter itself supplies the solar voltage. Site, load, solar and battery currents are now `None` when their power is. (#400)
* Hardware-validated on 2x Powerwall 3 (firmware 26.26.11, TEDAPI full mode) with a `trm_wifi` meter as the site's only solar meter: over 701 samples, 28 had zero solar, every one with `SolarMeterComms` active, and the alert never appeared with non-zero solar.
* tests: `test_tedapi_remote_meter.py` covers `trm_wifi` config/fetch/vitals recognition, the hierarchy `Timestamp`, and the SolarMeterComms hold (applied, including for a gateway solar of 1 W; not applied without the alert, with solar above the near-zero threshold or negative, for a reading older than the max age or more than the max age ahead of the gateway clock, applied for a reading a second newer than the status snapshot, without a reading or system timestamp, without a solar CT, or with a zero reading; missing load power; error isolation), and that a missing site/load/solar/battery power or `control: null` with voltage sources reporting no longer raises.
* fix(tedapi): native API prefers LAN again after v1r WiFi failover recovery - `get_native_api()` remembered the WiFi host ('last host that served us goes first') and `_lan_reset()` never cleared it, so every poll's native overlay kept hitting WiFi forever even with the LAN healthy; the sticky `customer_host` is now reset on recovery (token re-login on host switch already handled). The reset and `get_native_api()`'s host selection both run under `_customer_lock`, so a native fetch in flight on WiFi during the recovery can't re-stick it. (#401)
* fix(tedapi): the CLI test tool (`python -m pypowerwall.tedapi`) no longer crashes with `AttributeError`/`TypeError` when the gateway returns explicit JSON `null`s - in `control`, `control.systemStatus`, `control.meterAggregates`, meter entries (`realPowerW`, `location`), or config `site_info`/`battery_blocks`. When `control` is null because the gateway's site manager is not running (`system.sitemanagerStatus.isRunning: false` - a faulted or uncommissioned gateway), the warning now says exactly that and points to the Tesla app, instead of suggesting a firmware schema change. Raw payloads are still saved to `status.json`/`config.json` before parsing. (#404)
* docs: AGENTS.md now defines how release version numbers are chosen (SemVer: PATCH for fixes and internals, MINOR for anything new or newly observable that stays compatible, MAJOR ruled out by the no-breaking-changes rule). CONTRIBUTING.md no longer asks contributors to bump the version in their PR (that contradicted AGENTS.md); DESIGN.md links the rules.
* Library version bumped to `0.19.0` (minor bump: new `get` output and new `get`/`set` options in #406, and protobuf descriptor names changed in #410 - see its Compatibility note)

## v0.18.2 - Powerwall 3 Fan Speeds and Battery Block Fix

* feat(tedapi): Powerwall 3 fan speeds. Each PW3 inverter's two fans are requested as extra ComponentsQuery signals and passed through on its `TEPINV--<din>` vitals block as `PCH_FanSpeed_A`/`PCH_FanSpeed_B` (measured RPM) and `PCH_FanDuty_A`/`PCH_FanDuty_B` (drive duty cycle, %), `None` when unavailable. `TEDAPI.get_fan_speeds()` now reports them on PW3 (it returned `{}` there: the PW2 `PVAC_Fan_Speed_*` signals are always `None` on PW3), keyed `TEPINV--<din>` in `get_pw3_vitals()` order; new helper `extract_pw3_fan_speeds()`. Powerwall 2/+ output is unchanged. Hardware-validated on two PW3s (firmware 26.18.1). PW3 has no target-RPM signal, so the PW2 `PVAC_Fan_Speed_Target_RPM` name isn't reused. Like the PW3 temperatures (#390), PW3 fans need the default `tedapi_api_version="V2024_06"`: the V2026_06 signed `PW3Query` has its signal names inline in the signed text and doesn't include the fans, so under V2026_06 PW3 fan output stays `{}` as before. (#398)
* fix(tedapi): `get_battery_block(din)` returns the Powerwall 3 battery block (the per-Powerwall ComponentsQuery answer: `{"components": {"baggr", "bms", "hvp", "pch", "pws"}, "pw3Can": {...}}`) in basic/WiFi TEDAPI mode and for v1r followers routed over WiFi. Since it was added (v0.10.8) it read the answer from the config-file slot of the response (`config.recv.file.text`), which a query answer never fills, so every call returned `{}` and logged `Error Decoding JSON: Expecting value: line 1 column 1 (char 0)`; the gateway was answering all along in `payload.recv.text`, as `get_pw3_vitals()` reads it (verified on 2x PW3, firmware 26.18.1). The v1r LAN and `V2026_06` paths already read the right field and are unchanged. The failure shapes are unchanged: `{}` (logged, cached for `pwcacheexpire`) for an empty or malformed payload, `None` without a DIN or answer. The internal `config` flag on `_fetch_query()`/`_parse_response()`, used only by this call, is removed; config.json fetches keep `_parse_legacy_response(config=True)`. (#396)
* Library version bumped to `0.18.2`

## v0.18.1 - Tesla Tariff API and v1r WiFi Failover

* feat(tariff): read the site's utility tariff and update Time-of-Use settings - `pw.get_tariff()` / `pw.set_tariff(tou_settings)` (endpoints `/api/tesla/tariff_rate` and `/api/tesla/time_of_use_settings`). Cloud reads the Owner API tariff and FleetAPI reads `tariff_content` from site info; writes follow Tesla's `time_of_use_settings` contract (`tariff_content_v2`). Responses are normalized (e.g. `{"Message": "Updated", "Code": 201}`), a successful write invalidates the cached tariff, and TEDAPI (mock read, `None` on write) and local mode (`None`) fail cleanly. Thanks @nesys (#382)
* fix(cloud): recover when Tesla replaces or re-provisions a site - after a 404 for a site ID that's gone from the account, switch to the site with the same `gateway_id` (or unique `site_name`), or the only site on a single-site account, persist it to `.pypowerwall.site`, and retry once; with several sites and no match, leave the site unchanged and log an error. Serialized, rate-limited to one attempt per minute. Long-running processes no longer need a restart after a site change. (#382)
* fix(tedapi): v1r failover to the WiFi fallback host (`wifi_host`) now actually happens when the wired LAN is down. The v1r LAN and WiFi-fallback sessions retry once instead of 2-3 times, so a dead host fails in ~2x timeout instead of holding the per-method API lock long enough for callers' outer timeouts to abandon it (later polls then only saw `Timeout waiting for API lock` and never reached WiFi). And a start or LAN recovery probe with the LAN down now adopts the DIN over WiFi and serves data there, where it used to return None and never come up; the LAN retry backoff still doubles on each failed probe. Both hosts down still returns None. Basic (WiFi) and bearer TEDAPI sessions are unchanged. Thanks @erikgieseler, requested by @jasonacox-sam (#394).
* feat: new `failover` option on `Powerwall`, `PyPowerwallTEDAPI` and `TEDAPI` (default `True`, unchanged behavior — what the proxy and pypowerwall-server use). `failover=False` is strict: `connect()` tries only the configured mode (no fallback to FleetAPI/Cloud; with `retry_modes` it retries that mode), and in v1r mode the leader always uses the wired LAN — no switch to the WiFi host, no startup on WiFi, and `get_native_api()` stays on the gateway host — so a failed request returns `None` instead of being rerouted. Followers still use `wifi_host`, their only route in v1r mode. For scripts that test which modes and transports work. (#395)
* fix(tedapi): the v1r LAN recovery probe runs once per window. When the window opened, every concurrent getter (each holds its own per-method API lock) passed the unguarded check and reconnected at once — with the LAN down and a WiFi host up, N LAN logins and N WiFi DIN fetches per probe — and the failure counter could be bumped once per racing thread, pushing the next probe out extra backoff steps. One request now claims the probe while the others keep routing via WiFi; the failover state (including the #394 startup-on-WiFi path) changes only in a few small methods under one lock, never held across a network call; and LAN failures of requests already in flight when the failover tripped no longer escalate it. Backoff schedule unchanged (8 minutes, doubling to ~2 hours). (#395)
* fix(tedapi): a known v1r leader DIN is no longer cleared by a failed reconnect (recovery probe or `connect(force=True)`; `connect()` still returns `None`). Clearing it opened a window where concurrent requests saw DIN `None` — starting a second concurrent reconnect or signing LAN requests with `None` — and, when the WiFi host was also briefly unreachable, left every getter running a full reconnect each poll (ignoring the backoff) and returning "Not Connected" instead of serving via WiFi once it answered again. (#395)
* fix(tedapi): v1r without a `wifi_host` no longer stops trying the LAN after 3 failures. With nowhere to fail over to, the tripped state only returned `None` without trying — for 8 minutes, even after the LAN came back. Every request now tries the LAN, and data resumes on the first one that succeeds. (#395)
* fix(tedapi): `connect()` is single-flight. Getters under different per-method locks that all found no DIN each ran `connect()` at once: in WiFi/basic mode each cleared the DIN and closed the session other threads were mid-request on; in v1r mode each ran a full login + DIN + key probe. A caller that finds a connect in flight now gets the current DIN (`None` if still unknown) instead of starting another. (#395)
* fix(tedapi): `get_pw3_vitals()` no longer raises. It calls the transport directly, so a gateway timeout, connection reset or malformed payload propagated into `vitals()`, `get_blocks()` and `/api/meters/aggregates`; it now logs and returns `None`, and a transport error on one Powerwall skips only that Powerwall. Its result is now cached for the data-cache window, `pwcacheexpire` (the cache was read but never written, so one proxy poll re-queried every Powerwall three or more times). (#395)
* fix(tedapi): `@uses_api_lock` getters accept positional arguments: `get_battery_block("DIN")`, as the module docstring documents it, raised `TypeError` (multiple values for `self_function`). Keyword calls are unchanged. (#395)
* fix(tedapi): the cache read no longer raises `KeyError` when another thread (config-write invalidation) pops the entry mid-read, and treats an entry stamped in the future (wall clock stepped back) as expired instead of fresh. (#395)
* fix(tedapi): a successful WiFi TEDAPI request clears a WiFi cooldown another thread set while it was in flight. (#395)
* fix(v1r): transport read/write methods called without a DIN return their failure value (`None`/`False`) instead of raising from the signing code; the retry after a 401/403 re-login is re-signed (the signature expires 12 s after signing, which the first attempt plus the login can exceed); `write_config_v1r()` no longer raises internally on a non-filestore reply (`MessageEnvelope` has no `error` field) and reports failure for a filestore reply that isn't an update acknowledgement; `get_din()` handles a gzip-compressed body (as `/tedapi/din` sends on firmware 25.42.2+); concurrent key-auth failures emit their `UserWarning` once. (#395)
* docs: README "v1r WiFi Fallback" now documents the leader failover (it described only follower routing) and `failover=False`; API.md lists `tedapi_auth_mode` and `failover`. (#395)
* tests: new `test_failover_option.py`, `test_v1r_lan_probe.py`, `test_tedapi_hardening.py`, `test_v1r_transport_hardening.py`, and `proxy/tests/test_transport_health.py`. (#395)
* Library version bumped to `0.18.1`

## v0.18.0 - Modern Packaging and Clean Distributions

* build: packaging moved to a PEP 621 `pyproject.toml` (setuptools backend); `setup.py` is now a compatibility shim, so existing `python setup.py …` tooling keeps working. The version is a single plain `__version__` literal in `pypowerwall/__init__.py`, read at build time via setuptools' `attr:` (no import, no regex), replacing `setup.py`'s regex parse. The public `version` and `version_tuple` attributes are unchanged. Thanks @jasonacox-sam, prompted by @hulkster (#389, #388).
* fix(build): distributions no longer ship the repository's `proxy/` directory as a top-level `proxy` package. The 0.17.x wheels carried the proxy's `server.py` and tests, and — because a local `proxy/pypowerwall` symlink was followed at build time — a duplicate copy of the library (~85 files). Package discovery is now explicit (`pypowerwall*`), so neither can leak in. Nothing imported `proxy` from the installed package (the proxy's Docker image copies its files from the repo). (#389)
* build: declares `requires-python = ">=3.9"`, matching the CI-tested versions (Python 3.8 is end-of-life); pip keeps Python 3.8 environments on 0.17.x instead of offering an untested release. License metadata uses the PEP 639 SPDX form (`license = "MIT"`). (#389)
* fix: `version_tuple` is derived from `__version__` without raising, so a pre-release version string (e.g. `0.18.0rc1`) can't break `import pypowerwall`; it yields the numeric release components, `(0, 18, 0)`. (#389)
* build: the published dependency list now requires `requests-oauthlib>=1.3.0`, matching what CI tests (`requirements.txt`); a test keeps the two lists in sync. (#389)
* ci: new `Package` workflow builds the sdist and wheel on Python 3.9 and 3.13, runs `twine check --strict` and the new `tools/check_dist.py`, and installs each artifact into a clean venv to verify import, metadata version, data files, and that no `proxy` package ships. Run `python tools/check_dist.py dist` locally before publishing. (#389)
* Library version bumped to `0.18.0`

## v0.17.4 - Powerwall 3 Temperatures and Tesla Remote Meter

* feat(tedapi): Powerwall 3 temperatures are back. `temps()` (and the proxy's `/temps` and `/temps/pw`) now report the hottest battery-pack reading per Powerwall 3 and expansion pack; they returned `{}` on PW3 because the PW2 thermal-controller signal (`THC_AmbientTemp`) doesn't exist there. `vitals()` carries the full breakdown in degrees C: `HVP_PackTempMax`, `HVP_PackTempMin`, and `HVP_ShuntTemperature` (plus the `BMS_LOG_tempOutOfBounds` / `BMS_LOG_tempOutOfBoundsCharge` over-temperature event counters) on each `TEPOD--…` block, and the inverter's `PCH_AmbientTemp` (enclosure) and `PCH_heatsinkTemp` on each `TEPINV--…` block (`None` when unavailable; `PCH_heatsinkTemp` is passed through as delivered but reads a constant 45.45 on current firmware, so `temps()` doesn't use it). Hardware-validated on a PW3 leader + follower over WiFi TEDAPI and v1r LAN; `/temps/pw` `PWn` numbering matches `/pod`. (#390)
* feat(tedapi): the signals are requested through the existing signed V2024_06 ComponentsQuery — its signature covers only the query text, and the gateway honors additional `*SignalNames` variables. New `EXTRA_SIGNAL_NAMES` in `tedapi/queries/__init__.py` appends library-requested signals after the captured ones; the JSON captures are unchanged (see AGENTS.md, "Requesting additional TEDAPI signals"). The V2026_06 query set can't carry extra signals (names are inline in its signed text), so PW3 temperatures need the default `tedapi_api_version`. (#390)
* fix(tedapi): `get_pw3_vitals()` no longer fails outright when a component entry in the gateway payload is malformed (e.g. `None`) — the alert collection now guards it, and that battery still reports its energy. (#390)
* Additive only: PW2 `temps()` output is unchanged, and existing vitals fields and component signal positions are preserved. (#390)
* feat(tedapi): surface Tesla Remote Meter (wireless CT meter, config.json meter type `trm_mb`) data. `get_device_controller()`'s Device Controller Full query already requested `teslaRemoteMeter` and its docstring documented the field, but nothing read it - it was fetched and discarded on every poll. (#386)
  * `derive_meter_config()` gained a `types` filter parameter (default `("neurio_w2_tcp",)`, unchanged for existing callers) so the same config-driven CT/location/scale-factor lookup used for Neurio also works for remote meters (`types=("trm_mb",)`).
  * New `aggregate_remote_meter_data()` mirrors `aggregate_neurio_data()` but reads `teslaRemoteMeter.meters[].reading.ctReadings`, also carries the `energyImportedWs`/`energyExportedWs` lifetime accumulators, and keys its hierarchy by `"{din}:{ct index}"` (not just the CT slot) so a second remote meter can't overwrite the first; each entry keeps its own `Index` so consumers map CTs to phases by slot rather than iteration order.
  * New `get_remote_meter_readings()` fetches the Device Controller Full query (remote meter data isn't in the Basic query `get_status()` uses) and returns the aggregated CT hierarchy - but only when config.json declares a `trm_mb` meter, so installs without one never pay for the extra fetch.
  * `vitals()` now includes a `TRM--<din>` block per remote meter, alongside the existing `NEURIO--<serial>` blocks.
  * `/api/meters/aggregates` site section: extended the existing Meter X -> Meter Z -> Neurio fallback chain with a Remote Meter tier, reached whenever nothing produced a `site` CT (not only when Neurio is entirely absent - a Neurio assigned solely to solar/load no longer blocks the fallback).
  * `/api/meters/aggregates` solar section: voltage (PVAC) and current (Meter Y) sources are now independent, each falling back to a Remote Meter configured for the `solar` location on its own. A remote-metered solar circuit has no Meter Y at all, so `i_a_current`/`i_b_current`/`i_c_current` used to stay 0 even when PVAC reported voltage and a remote CT was actively reporting current.
  * `get_api_meters_aggregates()` fetches the remote-meter hierarchy once and shares it between the site and solar extractors instead of each fetching independently.
* tests: new `test_tedapi_remote_meter.py` (37 tests) covering the meter-type filter, CT scaling/location/multi-meter hierarchy keys, skipped-CT-slot phase mapping, the config-aware fetch skip, both fallback chains, the shared single-fetch, and the `vitals()` merge. (#386)
* Hardware-validated by the contributor against a Powerwall 3 with a wireless remote CT meter monitoring a solar circuit (#386).
* fix(tedapi): the `@uses_api_lock` getter locks (`get_config()`, `get_status()`, `get_device_controller()`, `get_firmware_version()`, `get_components()`, `get_battery_block()`) were stored on the function object, i.e. one lock per method shared by every `TEDAPI` instance in the process. A server polling several gateways (one `TEDAPI` each) therefore serialized all of them behind whichever gateway's fetch was in flight, and a slow or unreachable gateway starved the others into lock timeouts and stale-cache fallbacks. The locks now live on the instance, keyed by method name (`TEDAPI._api_lock()`), so gateways never wait on each other; per-method serialization within one gateway is unchanged. `acquire_lock_with_backoff()` accepts the lock itself in addition to the legacy `api_lock`-holder convention; `None` remains a no-op. (#381)
* tests: `test_tedapi_cached_fetch.py` gains `TestPerInstanceLocks` (a held lock on one instance no longer blocks another, per-method/per-instance identity, thread-safe lazy creation, no shared function attribute) and `TestAcquireLockWithBackoff` (#381)
* docs: bearer auth mode is documented as solar-only gateways only — it does not work on Powerwall 2 (hardware-tested) or Powerwall 3. Docstrings, CLI help, README and proxy docs corrected. (#380, #381)
* docs(v1r): corrected key-state semantics: state 2 is `PENDING_VERIFICATION_TIMEOUT` (the ~10-minute verification window closed), not a stage between 1 and 3 — re-registering the same key reopens it. Updated physical-proof step: switch the Powerwall 3 On/Off switch OFF for about 15 seconds, then back ON; a quick flick is debounced. README gains a Key States table and a note that some units answer v1r on their home LAN address. Thanks @LAE1990 (#383, #354).
* fix(register): `python -m pypowerwall register` now honors `-authpath` / `PW_AUTH_PATH` (it silently used the current directory, so re-registering could create a new key instead of reusing the configured one). Key-auth warnings now print the exact command that re-registers the configured key. (#383)
* fix(register): the post-proof poll watches for VERIFIED for up to 120 seconds (was ~25 s, shorter than the documented 62 s transition), and a timed-out key (state 2) skips the physical-proof prompt and goes straight to re-register guidance. (#383)
* Library version bumped to `0.17.4`

## v0.17.3 - PW3 v1r Islanding Commands

* fix(tedapi): make the existing `Powerwall.go_off_grid(confirm=True)` and `Powerwall.reconnect_grid()` methods work in PW3 v1r mode by sending Tesla's signed legacy `setIslandMode` command through TEDAPI. Hardware-validated on a Powerwall 3 using the v1r transport (#379).
* feat(tedapi): `TEGAPISetIslandModeRequest`/`TEGAPISetIslandModeResponse` added to the vendored `tedapi_combined.proto` (legacy TEG oneof fields 3/4) and the pb2 regenerated, so the islanding command flows through the existing `send_teg_message()` path — the generated encoder produces byte-identical wire output to the hardware-validated encoding, pinned by unit tests. The vendored `.proto` files are the single source of truth for the TEDAPI wire schema (see AGENTS.md).
* fix(tools): `gen_proto.sh` — replace GNU-only `sed -i -E` with portable `perl -pi -e` (BSD/macOS sed misparses `-i -E` as a backup suffix, corrupting the V2026_06 pb2 import rewrite on Mac)
* Library version bumped to `0.17.3`

## v0.17.2 - TEDAPI Getter and Bearer Transport Consolidation

* refactor(tedapi): the cached getters — `get_config()`, `get_status()`, `get_device_controller()`, `get_firmware_version()`, `get_components()`, `get_battery_block()` — were six hand-copied ~60-line variants of the same skeleton (cache check → cooldown → lock → re-check → connect → fetch → cache; lock timeout → stale cache). They now share one `_cached_fetch()` and contribute only their cache key, expiry and fetch; the query getters share one `_fetch_query()` (build → post, LAN or WiFi → parse → JSON). `get_din()` keeps its deliberately different contract (no lock, never reconnects, lets a transport exception reach `connect()` for its routing advice) but uses the same cache/cooldown helpers, with its three transports split out. `pwcache`/`pwcachetime` are unchanged as the storage. Behavior deltas, all deliberate:
  * `get_firmware_version(details=True)` on a warm cache now returns the details dict — the cache holds the `SystemInfo`, where it used to hold the version string and hand that back regardless of `details`
  * `get_firmware_version()`, `get_components()` and `get_battery_block()` now attempt `connect()` when the DIN is unknown, like the other getters already did, instead of failing the fetch on a `None` recipient
  * `get_battery_block()` now logs an empty payload as a JSON decode error (result unchanged, `{}`). Each query's answer to an empty/malformed payload is otherwise unchanged and now pinned per getter: `get_status()`, `get_device_controller()`, `get_battery_block()` and `get_config()` degrade to `{}` (logged) for the cache window; `get_components()` keeps its uncached `None` (`_fetch_query(..., strict=True)`) so the next poll retries, `get_pw3_vitals()` sees "no components" rather than an empty set, and the proxy's `/tedapi/components` keeps serving `null` rather than `{}` on failure
  * `get_config()` on v1r LAN gets the same `battery_blocks: []` default as the other transports; log lines are uniform (`Get <name> from Powerwall`, `Error fetching <name>: …`, `Using Cached <key> (age: …)`)
* refactor(tedapi): `get_config()` now fetches config.json through the shared transport (`_post_tedapi()` + the shared legacy parser) like every other query, instead of carrying its own inline bearer (`_authenv_post` + `MessageEnvelope` parse) and basic (`session.post` + busy/error/gzip handling) branches — one copy of the transport logic to keep in sync. The v1r WiFi-fallback path reuses the same `_build_config_request()` builder and parser. No behavior change: the basic branch of `_post_tedapi()` already had identical semantics (429/503 → 5-minute cooldown, non-200 → `None`, gzip decode).
* refactor(tedapi): the bearer transport no longer re-parses the request `Message` as an `AuthEnvelope` to find the inner envelope (a wire-shape pun on field 1). `_post_tedapi()` strips the `Message`/`Tail` wrapper to bare `MessageEnvelope` bytes with one shared `_envelope_bytes()` — the same strip the v1r LAN route uses, with the transport proto matched to `tedapi_api_version` so a V2026_06 signed-GraphQL request survives the round trip — and `_authenv_post()` now takes envelope bytes and wraps them verbatim. Bare-envelope input is passed through explicitly (protobuf parses it as an *empty* `Message` without raising, so an unguarded strip would send `b""`); the same guard now backs the v1r route's documented "full Message or bare envelope" contract.
* refactor(tedapi): `_parse_response()`'s legacy tier is split out as `_parse_legacy_response()`. config.json is the same legacy `config.send` protobuf on every api version (under V2026_06 the field parses as `filestore.readFileRequest`), so `get_config()` parses through it directly — routing a config fetch through `_parse_response()`'s version dispatch would hand it to the signed-GraphQL parser under V2026_06 (which bearer mode requires) and read back nothing. Query call sites are unchanged.
* tests: new `test_tedapi_cached_fetch.py` (106 tests — the shared skeleton parametrized over all six getters: cache hit/expiry/force, cooldown, lock timeout → stale cache, transport `None` → uncached, fetch exception → logged `None`, reconnect; plus per-getter transports, `get_din`'s contract, `_fetch_query`/`_decode_json`); `test_api_version.py`'s role-map guard also scans `_fetch_query(<role>)` call sites; `test_bearer_auth.py` reworked for the new contracts (+6 net) — `_authenv_post()` is handed envelope bytes; the wrapper-strip, bare-envelope passthrough, junk passthrough and V2026_06 strip tests live under `_post_tedapi()`; `get_config()` gains bearer + V2026_06 parse and end-to-end round-trip guards, a v1r WiFi-fallback config test, and an assertion that the fetch reaches `_authenv_post()` with the bare `config.send` envelope
* Library version bumped to `0.17.2`

## v0.17.1 - set_operation Partial Payload Fix (PW3 Mode-Persistence Race)

* fix(core): `set_operation()` no longer back-fills `/api/operation` payloads for partial-payload backends (cloud, fleetapi, tedapi) — only the fields the caller actually set are written. Tesla applies BACKUP_RESERVE and OPERATION_MODE as two asynchronous commands, so a back-filled reserve write raced a mode-only change and the mode command could be silently dropped on Powerwall 3 (most reproducible when the current reserve is 0). Local gateway writes keep the full-overwrite back-fill behavior, as before.
* fix(core): an explicit `level=0` is no longer coerced to boolean `False` — numeric `0` is preserved through payload construction, and the cloud/fleetapi "missing parameters" guards now treat `0` as present (`is None` checks)
* fix(core): calling `set_operation()` with neither `level` nor `mode` on a non-local backend now logs an error and returns `None` instead of posting an empty payload that would raise
* chore: corrected the cloud/fleetapi invalid-payload error message quoting and grammar
* tests: payload-construction regression tests across local vs non-local semantics, reserve-0 acceptance (cloud + new FleetAPI suite), and empty-payload soft-fail
* Library version bumped to `0.17.1`

## v0.17.0 - TEDAPI Bearer Authentication Mode

* feat(tedapi): new `bearer` authentication mode — logs in via `POST /api/login/Basic` with the installer credentials (full gateway password from the QR sticker) to obtain a Bearer token, then wraps every TEDAPI query in a protobuf `AuthEnvelope` with `externalAuth.type = PRESENCE`. Unlike `basic` (HTTP Basic Auth to `192.168.91.1`, which is only reachable over the Gateway's Wi-Fi), bearer also works over the Gateway's wired LAN IP. Hardware-verified on solar-only inverters over both a WiFi static route and the hardwired LAN IP. **Not supported on Powerwall 2 or Powerwall 3** — for PW3 wired access use v1r mode (`rsa_key_path`).
  * `Powerwall(..., tedapi_auth_mode="basic")` — new constructor parameter; `"basic"` (default) keeps existing HTTP Basic behavior, `"bearer"` selects the new transport. Forwarded through `PyPowerwallTEDAPI` to `TEDAPI(auth_mode=...)`.
  * New `AuthMode` str-enum (`pypowerwall/tedapi/auth_mode.py`) with `coerce(value, default=None)` — an unrecognized mode raises `ValueError` (never silently selects a different transport); callers that must not fail on a bad value (env vars) pass `default=` to get a logged warning and a fallback instead
  * TEDAPI CLI: new `--auth-mode basic|bearer` flag (`python -m pypowerwall.tedapi <gw_pwd> --auth-mode bearer`)
  * An expired or rejected token triggers a single transparent re-login and retry; `api_logout` now actually invalidates the bearer session (best-effort) and `api_login_basic` delegates to the bearer login — both were previously mock stubs
* **V2026_06 coupling:** bearer is the AuthEnvelope transport for the Tesla-signed GraphQL query set introduced in `V2026_06` — pair `tedapi_auth_mode="bearer"` with `tedapi_api_version="V2026_06"`. The check is a minimum, not an exact match (anything newer than V2026_06 also qualifies). `bearer` + `V2024_06` logs a warning but does not fail — wrapping the legacy QueryType queries in the AuthEnvelope transport may be rejected or answered only partially by the gateway, but existing setups keep working while the likely misconfiguration is surfaced. `bearer` + v1r raises `ValueError` (incompatible transports).
* fix(tedapi): `get_firmware_version()`/`_get_system_info()` now parse correctly under `V2026_06` + bearer — the bearer transport (like v1r) hands back a bare `MessageEnvelope`, not the full `Message` wrapper, and the envelope-class choice and the unwrap now follow the same bare/full test. The version gate also uses ordered comparison (`< V2026_06`) so future query sets inherit the V2026 path.
* feat(proxy): new `PW_TEDAPI_AUTH_MODE=basic|bearer` env var (default `basic`); applies to full TEDAPI mode (`PW_GW_PWD` set, `PW_PASSWORD` blank). An unrecognized env value warns and falls back to `basic` (via `AuthMode.coerce(..., default=AuthMode.BASIC)`) — a typo in a container env var shouldn't surface later as a fatal connection error and a restart loop. The active auth mode is reported in `/stats` and `/health`, and the proxy warns when the requested mode differs from the one the live client actually uses (hybrid mode builds its own TEDAPI and always speaks basic). `PW_TEDAPI_API_VERSION` and `PW_TEDAPI_AUTH_MODE` now appear in the `/stats` config dump.
* tests: new `test_bearer_auth.py` (55 tests — `AuthMode.coerce` strict and `default=` fallback paths, login/logout, AuthEnvelope wrap/unwrap, re-login on token expiry, V2026_06 coupling warning, v1r incompatibility) and `test_bearer_wiring.py` (22 tests — parameter plumbing `Powerwall` → `PyPowerwallTEDAPI` → `TEDAPI` and the CLI flag); `test_api_version.py` extended (+21 tests); new proxy `test_tedapi_auth_mode.py` (7 tests — env wiring and `/stats`/`/health` reporting)
* fix(tests): `Powerwall` fixtures in `test_powerwall_core.py` / `test_cloud_regressions.py` now patch the cloud backend by name — previously a cached `.pypowerwall.auth` in the working directory caused them to attempt real network access (masked in CI, which never has one)
* docs: README (`tedapi_auth_mode` parameter), proxy README (`PW_TEDAPI_AUTH_MODE`), and the `server.py` header gain a TEDAPI Mode section covering both settings
* Proxy BUILD bumped to `t100`; library version bumped to `0.17.0` (minor bump — new user-facing authentication transport)

## v0.16.5 - PW3 Lifetime Energy Accumulators via Gateway Local API

* feat(tedapi): lifetime `energy_imported` / `energy_exported` accumulators are now merged into the synthesized `/api/meters/aggregates` response for Powerwall 3 systems — resolving dashboards showing zero cumulative energy. (#221, #372)
  * PW3 firmware still serves the classic `/api/meters/aggregates` endpoint behind the customer login (`POST /api/login/Basic` → Bearer token); the TEDAPI adapter now fetches that native payload and overlays the energy fields (site/battery/load/solar) that the TEDAPI payloads do not carry
  * Works in both v1r wired-LAN mode and WiFi full-tedapi mode; password auto-derived the same way the library already does it
  * Merged sections carry a provenance note in their `disclaimer` (`…; energy from gateway local API`)
  * Gateways without the endpoint degrade gracefully — values stay `0` exactly as before, with a 5-minute retry backoff so unsupported firmware isn't hammered; successful fetches are cached on the normal poll cadence
  * Thread-safety hardening for the proxy's multi-threaded use: bounded lock acquisition with stale-cache fallback on contention (no unbounded queuing behind a slow fetch), double-checked cache inside the lock (no thundering-herd refetch on cache expiry), and last-good-host/`lan_failed`-aware host ordering so a dead wired LAN doesn't add a full timeout to every poll
  * Verified against a live Powerwall 3 (firmware 26.x): values cross-check against solar/grid/battery/load power flows and tick upward between polls

## v0.16.4 - TEDAPI Auto-Recovery Wedge Fix

* fix: `Powerwall.connect()` now restores `tedapi`/`tedapi_mode` along with `mode`/`cloudmode`/`fleetapi` when all connection modes fail. Previously a fully-failed `connect(retry=False)` left `tedapi=False` behind (the local-mode fallback handler zeroes it), which permanently wedged the proxy's TEDAPI auto-recovery thread — its `pw.tedapi` gate short-circuited every iteration, so no further recovery attempt was ever made until restart. (#366)

## v0.16.3 - TEDAPI API Version Ordering and Content-Type Fix

* feat(tedapi): `TEDAPIApiVersion` members are now ordered by the date their label encodes; comparing against anything that is not a known version now raises `TypeError` (previously fell back to silent lexical string comparison). (#363)
* fix(tedapi): correct Content-type request header typo `application/octet-string` → `application/octet-stream` (RFC 2046) in the library and the standalone `tools/tedapi` scripts; gateway does not validate the header (#364)

## v0.16.2 - TEDAPI Fallback, v1r Diagnostics, and Firmware Version Improvements

* feat(proxy): TEDAPI SolarOnly fallback mode — when TEDAPI connectivity is lost, the proxy automatically continues serving solar data without interruption. Enabled via `PW_TEDAPI_RECOVERY=yes`. (#361)
  * Background probe/recovery thread polls every `PW_TEDAPI_PROBE_INTERVAL` seconds (default 30, minimum 5); after 3 consecutive failures the proxy enters SolarOnly fallback
  * Automatic recovery with exponential backoff (60s → 300s max); reconnect is hardware-verified: fallback triggered at ~T+165s, recovered in 60s on first attempt against live PW3+follower
  * `/health` and `/stats` now include a `fallback_mode` block (`is_fallback_mode`, `reason`, `entered_at`, `recovery_attempts`, `last_recovery_attempt`)
  * `POST /health/reset` resets fallback state and triggers an immediate recovery attempt
  * Note: `pw.connect()` is called on the live proxy thread during recovery — this is the first code path to do so at runtime while handler threads are active; the design trade-off (no restart needed vs. brief in-flight request impact) is documented in `server.py` and `proxy/RELEASE.md`
* fix(v1r): `PENDING_VERIFICATION` and `UNKNOWN_KEY_ID` auth warnings now surface at normal log level — previously required `PW_DEBUG=yes` to see, leaving users with no indication of key enrollment problems. (#355)
  * Key fingerprint logged on auth failure; `pending_verification` flag resets on successful recovery; probe cache seeded after reconnect
* feat(tedapi): `get_firmware_version()` refactored onto a unified `_get_system_info()`/`SystemInfo` model — produces identical output across `V2024_06` and `V2026_06` query sets, and across basic and v1r transports. New TEDAPI CLI flags `-firmware`/`-details` expose it directly. (#356)
* fix(tedapi): v1r WiFi-fallback responses normalized at the transport boundary — `_post_tedapi()` now re-extracts the bare `MessageEnvelope` bytes from the full WiFi `Message` wrapper. Previously the wrapper was returned as-is; protobuf's lenient decoding silently produced empty/incorrect data (e.g. blank firmware version) whenever the LAN→WiFi fallback fired. (#356)
* **BREAKING (approved exception):** `get_firmware_version(details=True)` renames `system.five` → `system.systemUpdate` and `system.six` → `system.deviceType`, and surfaces previously-dropped `installedFirmwareSignature`/`offlineFirmwareSignature` fields. Tesla's own gateway frontend (`app.js`) uses `systemUpdate`/`deviceType`; the old names were MITM reverse-engineering placeholders. No known downstream consumers — Powerwall-Dashboard, the pypowerwall facade, and the proxy do not read these fields. (#356)
* fix(proxy): Docker `HEALTHCHECK` now uses `curl` — the official Alpine image includes `curl` but not `wget`; the prior `wget`-based check always failed silently. (#357)
* fix(cli): `Ctrl-C` now exits cleanly instead of printing a traceback
* Proxy BUILD bumped to `t97`; library version bumped to `0.16.2`

## v0.16.1 - Windows TLS Fix for Tesla Auth

* fix(windows): cap TLS to 1.2 on Windows to avoid Tesla token fingerprint rejection (#350)
  * Windows Python bundles an OpenSSL build whose TLS 1.3 ClientHello fingerprint is rejected by Tesla during PKCE code exchange and token refresh — tokens come back "tainted" and all `owner-api.teslamotors.com` calls return `403 Forbidden`
  * `_httpx_auth_verify()` in `tesla_auth.py` and `teslapy/__init__.py` now caps `maximum_version` to TLS 1.2 on Windows (`sys.platform == 'win32'`); Linux/macOS retain TLS 1.3 pinning
  * TLS 1.2 fully supports HTTP/2, so ALPN negotiation and h2 framing are unaffected
* fix(register): `api_call()` in `v1r_register.py` now uses httpx with HTTP/2 for Tesla API endpoints (was urllib/HTTP/1.1)
  * Tesla now requires HTTP/2 for `owner-api.teslamotors.com/api/1/*` calls (June 2026)
  * Falls back to urllib for non-Tesla URLs or if httpx is not installed
* docs(windows): README updated with Windows setup troubleshooting — native Windows TLS, WSL2 WebKitGTK limitation, and alternatives (tesla_auth app, full Linux VM, remote authtoken)
* diagnostics: `cloudcheck` now reports platform-aware TLS behaviour on Windows

## v0.16.0 - Code Review Fixes: Correctness, Security, and Robustness

Full-codebase review sweep (see `docs/code-review-2026-07-03.md` for the complete findings). 104 new regression tests (227 passing, up from 123). No public API signatures or return shapes changed. Hardware-verified against production proxies with `proxy/regression_test.py`: all 76 non-control endpoints byte-compatible across TEDAPI WiFi, v1r+WiFi hybrid, Cloud, and FleetAPI modes.

* fix(core): `set_operation()`/`set_mode()` no longer silently lowers the real battery reserve — the reserve back-fill is now scale-aware per backend (raw for local, app-scale for cloud/fleetapi/tedapi) and guards an unreadable reserve
* fix(core): `alerts(alertsonly=False)` crashed with `TypeError` since introduction; device alerts now returned as `{device: alert}` dicts as documented
* fix(core): a fully-failed `connect()` no longer leaves the facade without a client (raw `AttributeError` on every call) or with a mutated fallback mode; `retry_modes` indefinite blocking documented
* fix(fleetapi): token refresh could permanently wedge the client via a stuck `refreshing` flag; now lock-based with proper error handling
* fix(fleetapi): reuse one HTTP/2 client (was a TLS handshake per request); never re-send a POST via the HTTP/1.1 fallback after it may have been transmitted (duplicate write commands); stop caching errors and unique history URLs
* fix(tedapi): `available_blocks` always 0 (read from wrong payload); `PINV_GridState` always None (copy-paste); PW3 vitals None-crashes; POD/PINV bounds guards; lock timeouts return cached data instead of raising; 429/5xx no longer misclassifies PW2 as PW3; sessions closed on reconnect and `close_session()` (note: `TESYNC--None--None`/`TESLA--None` vitals blocks are intentionally kept - `TESLA--None` carries the gateway DIN in `componentParentDin`)
* fix(cloud): `set_grid_charging`/`set_grid_export` returned a raw tuple; `post_api_operation` failed on partial payloads and `False` reserve; racy `_site_api` flag replaced with real per-name locks; sitefile parse failure falls back to auto-select
* fix(local): documented `poll(api, raw=True)` now works; negative caching (404/403/503) now actually suppresses re-requests; missing Content-Type and None firmware version no longer raise
* fix(security): credential files (`.pypowerwall.auth`, `.pypowerwall.fleetapi`, `.powerwall`, v1r RSA keys/tokens) created with `0600` permissions atomically; tokens/secrets redacted from debug logs
* fix(cli): `-local` without `-host` errors clearly instead of silently using cloud mode; `set -current` handles unavailable battery level
* feat(docs): new `AGENTS.md` and `DESIGN.md` (architecture, conventions, invariants for contributors and AI agents); README/API docs corrected against the code
* refactor: shared None-safe `lookup()` and mock-data decorator in `pypowerwall/helpers.py` (ends three-way copy drift; existing import paths preserved)
* Proxy hardened separately — see `proxy/RELEASE.md` t95
* Bump library version to `0.16.0` (minor bump to signal the breadth of behavioral fixes; no public API signatures or return shapes changed)

## v0.15.13 - Fleet API HTTP/2 Upgrade

* feat(fleetapi): upgrade Fleet API transport to HTTP/2 with TLS 1.3 (#338)
  * Proactively upgrades Fleet API transport to HTTP/2 — Fleet API currently works over HTTP/1.1, but HTTP/2 improves reliability and future-proofs against enforcement (Tesla has already enforced HTTP/2 on Owner API endpoints)
  * All 9 `requests` call sites in `fleetapi/fleetapi.py` replaced with `_http2_request()` helper
  * New HTTP/2 transport helpers: `_httpx_auth_verify()`, `_HTTP2Response`, `_http2_request()`
    * `_httpx_auth_verify()` — pins TLS 1.3 via `ssl.SSLContext` when available
    * `_HTTP2Response` — `requests.Response`-compatible wrapper for `httpx` responses (`.status_code`, `.text`, `.json()`, `.raise_for_status()`)
    * `_http2_request()` — unified request helper: tries HTTP/2 first, falls back to HTTP/1.1 on any error (logged as warning)
  * Form-encoded `data=dict` correctly routes to `httpx data=` kwarg; raw bytes/str use `content=`
  * `raise_for_status()` correctly distinguishes 4xx (Client Error) from 5xx (Server Error)
  * Follows same pattern as PR #324 (Cloud mode HTTP/2 upgrade in `teslapy/__init__.py`)
  * HTTP/2 enabled when `httpx[http2]>=0.27.0` is installed (already in `requirements.txt`); falls back to `requests` (HTTP/1.1) if unavailable
  * Hardware-validated against live PW3 (fw 26.18.1): Fleet API read, write (set/reset reserve), and protocol negotiation all confirmed ✅
* Bump library version to `0.15.13`

## v0.15.12 - Remote Setup and Cloud Auth Improvements

* fix(cloud): Docker/container headless setup no longer fails with 403 on first connect (#333)
  * Root cause confirmed: `owner-api.teslamotors.com` requires a **code-exchange AT** (from PKCE WebView login) to bootstrap the session. A "cold" refresh (RT used immediately with no prior code-exchange AT) is rejected with 403. Once the session is bootstrapped, normal RT-based refresh works — the service self-heals automatically after the initial ~8h AT expiry.
  * `authtoken` command now outputs **both** the Refresh Token (RT, valid 90 days) and Access Token (AT, valid ~8h) — RT shown first in both terminal output and window UI
  * macOS WebView success page redesigned: RT with green badge first, AT with yellow badge second, separate Copy RT / Copy AT buttons
  * `setup -headless` now prompts for RT first, then AT (required to bootstrap the session on first connect)
  * Both tokens are saved to the auth file; `connect()` uses the code-exchange AT directly on first connect
  * `connect()` now handles 401 (expired AT) by refreshing via RT and retrying — warm refresh works, so no manual token renewal needed after initial setup
  * `expires_at` in auth file now set to `now + expires_in` (real expiry, ~8h) when AT is saved, rather than always `0` — allows accurate expiry reporting in `cloudcheck` and auth file inspection
* feat(cloud): New `cloudcheck` diagnostics command for cloud mode troubleshooting
  * Checks Python, platform, OpenSSL version, TLS 1.3 support
  * Checks httpx and h2 installation and versions
  * Checks proxy environment variables
  * Decodes and validates auth file: detects empty AT, expired AT, and whether AT has code-exchange markers (`owner-api` aud, `x-enc` present)
  * Live connectivity test to `auth.tesla.com` and `owner-api.teslamotors.com` (HTTP/2 protocol check)
  * Optional token refresh test with informative failure messages explaining the code-exchange AT requirement
  * `cloudcheck -noconnect` skips live tests for offline validation
  * Adding `-debug` to `setup`, `cloudcheck`, or `authtoken` automatically prints a full environment diagnostics header (Python, platform, OpenSSL, httpx, h2, proxy vars) before running the command
* fix(cloud): Remove stale energy-scope comments and contradictory `SCOPES` documentation across `tesla_auth.py`, `teslapy/__init__.py`, `pypowerwall_cloud.py`, and `__main__.py`
  * Energy scopes (`energy_device_data`, `energy_cmds`) are NOT required and were a red herring
  * Updated `AUTH.md` Section 7 to mark RCA-6 (energy scopes) as **DISPROVEN** and document the confirmed root cause as RCA-8 (code-exchange vs refreshed AT)
* Bump library version to `0.15.12`

## v0.15.11 - HTTP/2 for Tesla Owner API Calls

* fix(cloud): Extend HTTP/2 support to all owner-api.teslamotors.com API calls, not just auth endpoints (#324) - t93
  * Tesla now requires HTTP/2 for `owner-api.teslamotors.com/api/1/*` endpoints, matching the auth.tesla.com requirement
  * Pin `httpx` Tesla auth/API transports to TLS 1.3 when possible, mirroring the TeslaMate fix path for Tesla endpoints while preserving explicit custom `verify` settings
  * `Tesla.request()` now routes owner-api calls through `httpx` with HTTP/2 when available, with automatic fallback to `requests` (HTTP/1.1)
  * `_request_http2` now forwards all session headers (`Content-Type`, `X-Tesla-User-Agent`, `User-Agent`) to httpx instead of a minimal subset — ensures Tesla receives the same fingerprint as the original requests session
  * Adds `_HTTP2Response` wrapper class for requests/httpx response compatibility
  * Fixes 403 errors during `setup` flow (sitelist retrieval) reported in Powerwall-Dashboard #779
  * Fixes 403 errors during normal cloud-mode polling (PRODUCT_LIST, SITE_DATA, etc.)
  * Requires `httpx[http2]>=0.27.0` — the `[http2]` extra installs `h2`, which is required for HTTP/2 support; without it, httpx silently falls back to HTTP/1.1

## v0.15.10 - Combined Reserve + Mode Control Endpoint

* feat(proxy): Optional companion parameters on `/control/reserve` and `/control/mode` POST endpoints to update both reserve and mode in a single `set_operation()` call (#308) - t90
  * `/control/reserve` now accepts optional `mode=$MODE` parameter — calls `set_operation(level, mode)` instead of `set_reserve(level)`
  * `/control/mode` now accepts optional `level=$RESERVE` parameter — calls `set_operation(level, mode)` instead of `set_mode(mode)`
  * Prevents duplicate Tesla audit-log entries caused by calling set_reserve + set_mode separately
  * Invalid companion values return a 400 error without making any Powerwall call (no silent fallback)
  * Full backward compatibility: omitting the companion parameter preserves original behavior
  * Added unit tests for all code paths (legacy single-value, combined, and invalid companion)
  * Updated proxy README with combined-request examples

## v0.15.9 - Improved Connection Error Diagnostics

* Fix: Promote connection failure messages from `debug` to `error`/`warning` log level so users see actionable diagnostics without enabling debug mode (#160)
  * Login failures in local mode now show `error`-level messages with specific guidance (check password, check network reachability)
  * Login errors now distinguish between auth failures (401/403 → "check password") and connectivity failures (other HTTP status → "check gateway reachability")
  * Connection attempt fallback messages (Local → FleetAPI → Cloud) promoted from `debug` to `warning` level, including the exception details
  * API timeout and connection errors during polling now log at `error` level with the affected endpoint and host
  * Connection refused errors include the specific exception message
* Fix: Final "Unable to connect to Powerwall" error message now includes guidance to verify host, credentials, and network connectivity, and suggests enabling debug logging for more detail
* Bump library version to `0.15.9`

## v0.15.8 - authpath Support for v1r Setup Files

* Fix: `python -m pypowerwall setup -v1r -authpath <dir>` now correctly writes all generated files into the specified directory instead of the current working directory
  * `tedapi_rsa_private.pem` and `tedapi_rsa_public.der` are written to `<authpath>/`
  * `fleet_tokens.json` (Fleet API path) is written to `<authpath>/`
  * `<authpath>/` directory is created automatically if it does not exist
* Fix: `python -m pypowerwall get -v1r -authpath <dir>` now auto-discovers `tedapi_rsa_private.pem` in `<authpath>/` when `-rsa_key_path` is not explicitly specified
  * Lookup order: `<authpath>/tedapi_rsa_private.pem` → `./tedapi_rsa_private.pem` → error with path hint
* Refactor: Removed stale `RSA_PRIVATE_KEY_FILE` and `RSA_PUBLIC_KEY_FILE` module-level globals from `v1r_register.py` — file paths are now resolved dynamically from `authpath` at call time
* Refactor: Removed stale `TOKENS_FILE` module-level global from `v1r_register.py` — tokens file path is now resolved from `authpath` and threaded through `step2_exchange_token(tokens_file=...)`
* Bump library version to `0.15.8`

## v0.15.7 - Grid Noise Suppression and v1r Owner API Login Fix

* Docs: Document Tesla cloud/FleetAPI 80% backup reserve limit
     * Added warning in README and CLI examples for `set -reserve` when using cloud or FleetAPI mode
     * CLI now prints a WARNING when attempting to set reserve above 80% in cloud/FleetAPI mode, and a NOTE if Tesla caps the actual value
     * Added v1r LAN mode example showing how to set reserve above 80%
* Feat: Add `PW_SITE_ZERO_THRESHOLD` environment variable to suppress phantom grid noise readings
  * When set to a positive integer value (in watts), site power readings with absolute value at or below the threshold are reported as 0
  * Applies to `/api/meters/aggregates` site power, `/csv`/`/csv/v2` grid power, and `/json` grid power endpoints
  * Useful for off-grid and night-time scenarios where sensor noise causes small non-zero grid readings (e.g. 5–15W phantom draw)
  * Default is `0` (disabled — no suppression)
* Proxy build t89
* For /json endpoint, None values are now preserved. Previously, the proxy converted None to 0 for numeric fields, which could cause confusion when distinguishing between true zero values and missing data. Now, if a field is None in the underlying API response, it will be returned as None in the /json output, allowing clients to handle missing data appropriately. The /csv and /csv/v2 endpoints continue to convert None to 0 for numeric fields to maintain consistent numeric output.
* Fix: v1r Owner API registration (`python -m pypowerwall setup -v1r` → option 1) now uses the native `tesla_auth` WebView PKCE flow instead of the broken `teslapy` browser redirect. The `tesla://` custom URL scheme callback is intercepted by the WebView, eliminating the "missing_code" login failure (#300, reported in discussion #299)
* Fix: Cached token lookup in `owner_api_login()` now selects the account matching the requested `email` argument instead of always using the first entry in `.pypowerwall.auth`
* Bump library version to `0.15.7`

## v0.15.6 - Reserve Percent Scaling Fix + CLI Redesign

* Fix: `set_operation()` reserve percent scaling — reverse Tesla App scaling (0–100%) to raw API scale (5–100%) only in TEDAPI v1r mode, avoiding incorrect round-trip values in cloud and FleetAPI modes
* Fix: Correctly handle `level=0` in `set_reserve()` via `level is not None` check
* Fix: Revert universal scaling from `set_operation()`; move raw conversion into `PyPowerwallTEDAPI.post_api_operation()` where it belongs
* Fix: FleetAPI `get_api_system_status_soe()` was returning `battery_level()` (Tesla App-scaled, 0–100% usable) directly as the raw SOE percentage — missing the reverse-scaling applied by the cloud backend. This caused `level()` (default `scale=False`) to return the already-scaled app value instead of the physical percentage, making FleetAPI SOC appear ~2% lower than v1r/TEDAPI for the same battery. Fix: apply `soe = (percentage_charged + 5/0.95) * 0.95` to convert app scale → raw, matching the cloud backend.
* Fix: `get` command now reports SOC using `level(scale=True)` — matching the Tesla app display (usable capacity, 0–100% of non-reserved energy) rather than the raw physical percentage including Tesla's 5% buffer reserve.
* Fix: FleetAPI config validation in `Powerwall.__init__()` — changed `os.access(file, W_OK)` check (fails when file doesn't exist) to check directory writability when config file is absent, preventing spurious `PyPowerwallInvalidConfigurationParameter` on first-time setup
* Feat: CLI (`python -m pypowerwall`) redesigned for consistency across all connection modes
    * Replace string `-mode` flag on `get` (which clashed with `set -mode`) with explicit boolean connection flags: `-local`, `-cloud`, `-fleetapi`, `-tedapi`, `-v1r` — available on both `get` and `set`
    * **Backward compat:** `get -mode <value>` still accepted with a deprecation warning; e.g. `get -mode v1r` behaves identically to `get -v1r`
    * Add `-host`, `-password`, `-gw_pwd`, `-rsa_key_path` credential flags to `get` and `set` subcommands
    * Add global `-debug` and `-authpath` flags (via shared parent parser) available to every subcommand
    * `setup` subcommand now handles all auth flows: default/`-cloud` (Tesla Owners API), `-fleetapi` (Fleet API wizard), `-v1r` (RSA key registration) — replacing the now-deprecated `fleetapi` top-level command
    * `get` output expanded: adds `firmware`, `grid_status`, and `time_remaining` fields; `None` values display as `N/A` in text/CSV output
    * Pre-flight checks in `get` and `set`: if `-cloud` or `-fleetapi` is specified but the required config file is missing, a clear error message with setup instructions is printed before any connection attempt
    * Connection check (`is_connected()`) now runs before the output banner — no partial output on failure
    * `fleetapi` top-level command shows deprecation warning and points to `setup -fleetapi`; `login` command shows deprecation warning and exits
* Docs: Update `README.md` CLI section — new command list with global flags, connection mode flag reference table, examples for all 5 connection modes, updated setup commands (`fleetapi` → `setup -fleetapi`, `setup -v1r`)
* Release prep:
     * Bump library version to `0.15.6`
     * Update proxy pinned dependency to `pypowerwall==0.15.6`

## v0.15.5 - Native Python Tesla Authentication + v1r Key Verification Fixes

* Feat: Replace external `tesla-auth` binary dependency with native Python Tesla authentication — no more platform-specific binary downloads
* Feat: New `setup` command handles authentication and site selection in a single flow using a native WebView popup window (macOS, Windows, Linux)
* Feat: New `authtoken` command for obtaining a refresh token on a local machine, then using it on a remote/headless server
* Fix: Cross-platform WebView interception of `tesla://auth/callback` using WKWebView (macOS), WebView2 (Windows), and WebKit2GTK (Linux)
* Fix: `v1r_register.py` now verifies the specific newly-registered RSA key rather than any key in the authorized clients list — prevents false VERIFIED result when only the Tesla app key is verified (fixes #274)
* Fix: `tedapi_v1r.py` now detects and clearly logs `client authorization not verified` inner-payload errors, with actionable instructions to complete physical key verification — previously silently returned `None` with no diagnostic output
* Release prep:
     * Bump library version to `0.15.5`

## v0.15.4 - CLI Enhancements and Safety Guards

* Feat: `pypowerwall tedapi` CLI now accepts `-host HOST`, `-gw_pwd GW_PWD`, `-v1r`, `-password PASSWORD`, `-rsa_key_path RSA_KEY_PATH`, and `-wifi_host WIFI_HOST` flags, enabling full PW3 wired LAN (v1r) access directly from the command line
* Feat: `go_off_grid()` now requires `confirm=True` to prevent accidental islanding — calling without the flag logs an error and returns `None`
* Fix: Unsupported-method error logs in `go_off_grid()` and `reconnect_grid()` now include the backend class name for easier diagnosis
* Add: Unit tests for `go_off_grid()` confirm guard and CLI v1r argument forwarding/password derivation
* Release prep:
     * Bump library version to `0.15.4`
     * Update proxy pinned dependency to `pypowerwall==0.15.4`

## v0.15.3 - PW3 No-Solar None Handling

* Update scanner to use cidr by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/266
* Add go_off_grid() and reconnect_grid() for Powerwall island mode control by @bolagnaise in https://github.com/jasonacox/pypowerwall/pull/277
* Fix: Prevent `TypeError` in Powerwall 3 TEDAPI vitals parsing when `PCH_PvVoltage*` or `PCH_PvCurrent*` signals are `None` on systems without solar panels - by @anopheles in https://github.com/jasonacox/pypowerwall/pull/278
     * `get_pw3_vitals()` now guards `None` values before performing `> 0` comparisons
     * PV measured voltage, current, and power now safely report `0` when the gateway returns missing PV values
     * Prevents downstream failures in endpoints derived from PW3 vitals, including `/api/meters/aggregates`
     * Adds regression coverage for PW3 systems without solar panels so the no-solar path no longer raises and remains locked in by tests

* Release prep:
     * Bump library version to `0.15.3`
     * Update proxy pinned dependency to `pypowerwall==0.15.3`
     * Fix PyPI upload cleanup script to remove `pypowerwall.egg-info` instead of stale `tinytuya.egg-info`

## v0.15.2 - Minor Fixes

* v0.15.2 - Protobuf Support by @jasonacox in https://github.com/jasonacox/pypowerwall/pull/276
* Fix: Remove `<5` upper cap on `protobuf` runtime dependency — constraint is now `protobuf>=4.25.1`; pb2 files generated with 4.25.x are compatible with 5.x, 6.x, and 7.x runtimes (confirmed and tested up to 7.34.1) and the cap was causing pip conflicts for users with newer protobuf versions installed (e.g. via TensorFlow)

## v0.15.1 - Code Quality and Build Pipeline Improvements

* Fix: Remove duplicate stub methods `get_grid_charging()` and `get_grid_export()` in `pypowerwall_tedapi.py` that were left over from a merge — the real implementations (reading/writing config via v1r transport) were already present and being shadowed
* Fix: Update `pwsimulator` `stub.py` to use `ssl.SSLContext` API replacing the removed `ssl.wrap_socket()` call, which caused the simulator container to silently exit on Python 3.12+
* Fix: Remove `linux/arm/v7` platform from `pwsimulator` Docker build (`upload.sh`) — platform is no longer supported
* Fix: Correct protobuf runtime dependency — `protobuf>=3.20.0` was misleading; set floor to `protobuf>=4.25.1` (the `<5` upper cap added here was subsequently lifted in v0.15.2)
* Add: `.pylintrc` with `[MESSAGES CONTROL]` disable list (restored), `[SIMILARITIES]` config, and `ignore-paths` to skip auto-generated `*_pb2.py` files
* Add: `tools/gen_proto.sh` — script to regenerate all `*_pb2.py` files from `.proto` sources using pinned `grpcio-tools`
* Add: `tools/requirements-tools.txt` — pinned dev tools (`grpcio-tools<1.64`, `protobuf<5`) to ensure pb2 files are generated consistently with a compatible protobuf version
* Add: `.pre-commit-config.yaml` — pre-commit hooks for protobuf regeneration and `pylint -E` checks on `pypowerwall/` and `proxy/` before every commit
* Add: `.github/workflows/check-protobuf.yml` — CI workflow to verify committed `*_pb2.py` files are in sync with their `.proto` sources

## v0.15.0 - Powerwall 3 Wired LAN TEDAPI Support (v1r)

* Docs: Note FleetAPI/Cloud mode requirement for `get_grid_charging()` and `get_grid_export()` - by @jasonacox-sam in https://github.com/jasonacox/pypowerwall/pull/268
* Insert empty `battery_blocks` array if missing to prevent downstream KeyError - by @zi0r in https://github.com/jasonacox/pypowerwall/pull/269
* Fix: Prevent shared-state race condition in stubs via factory functions - by @woofiwoof in https://github.com/jasonacox/pypowerwall/pull/270
    * `API_METERS_AGGREGATES_STUB` and `API_SYSTEM_STATUS_STUB` in cloud/fleetapi/tedapi stubs were module-level mutable dicts; concurrent polling of multiple gateways caused threads to overwrite each other's data
    * Replaced module-level dicts with `_..._TEMPLATE` constants and factory functions that return `copy.deepcopy()` copies, ensuring each gateway gets an independent data structure
* Add `/tedapi/v1r` transport for Powerwall 3 wired LAN access without requiring WiFi connection to `192.168.91.1` - by @nalditopr in https://github.com/jasonacox/pypowerwall/pull/265
    * New `tedapi_v1r.py` RSA-signed transport class — handles TLV payload construction, PKCS1v15+SHA512 signing, RoutableMessage protobuf wrapping, and Bearer token authentication
    * New `tedapi_combined_pb2.py` — compiled protobuf definitions for v1r message format (`RoutableMessage`, `MessageEnvelope`, etc.)
    * New `pypowerwall register` CLI command (and `v1r_register.py` script) for generating an RSA-4096 key pair and registering it with the Powerwall via Tesla Owner API (default) or Fleet API OAuth
    * `Powerwall()` constructor accepts new `rsa_key_path` parameter — when provided alongside `password`/`gw_pwd`, the library automatically selects v1r mode
    * `gw_pwd` (full 10-character QR code password from the Powerwall sticker) auto-derives the last-5-character Basic API password, simplifying configuration
    * Proxy server supports new `PW_RSA_KEY_PATH` environment variable to pass the RSA key path through to `Powerwall()`
    * `cryptography` package added to `install_requires` for RSA key loading and signing
    * Full feature parity with WiFi TEDAPI (mode 4): config, status, vitals, firmware version, power, battery level, grid status, per-device vitals, and component queries
    * LAN control support — set backup reserve, operation mode, grid charging, and grid export directly over the wired LAN via v1r filestore config writes (no cloud API needed)
    * WiFi fallback transport — when both wired LAN and WiFi TEDAPI are available, v1r mode transparently uses WiFi for follower queries; mode string dynamically reflects active transports (e.g., `Local (v1r+wifi+control)`)
    * Requires the Powerwall 3 leader's ethernet port to be on a routable subnet (`10.42.1.x/24` is the TEG's dedicated wired interface); see PR notes for bridge setup examples
* Drop `linux/arm/v7` (32-bit ARMv7) platform support from the pypowerwall proxy Docker container builds

## v0.14.10 - Host Port Support

* Add support for `host:port` format in the `host` parameter for local mode connections - Fix for https://github.com/jasonacox/pypowerwall/issues/254
     * Allows specifying a non-standard HTTPS port (e.g. `192.168.1.50:8443` or `powerwall.local:8443`)
     * Defaults to port 443 when no port is specified in `host`
     * Enables travel router / NAT proxy setups where multiple Powerwall gateways are each mapped to distinct `ip:port` endpoints on the local network
     * Updated `_validate_init_configuration()` to validate bare host first, then strip the optional port suffix — prevents false port detection inside IPv6 addresses (e.g. `2001:db8::1` is never mistaken for a host with port `1`)
     * Fixed TEDAPI hybrid mode detection in `PyPowerwallLocal` to match `192.168.91.1:443` (explicit default port) in addition to bare `192.168.91.1`, ensuring TEDAPI activates for direct gateway connections regardless of whether the port is stated
     * URL construction in local and TEDAPI modes naturally handles `host:port` format via `https://{host}/...` string formatting
     * Note: IPv6 addresses are accepted by validation but full URL construction support (bracket notation per RFC 2732) is not yet implemented

## v0.14.9 - TEDAPI Voltage Calculation Fix

* Fix `compute_LL_voltage()` function to handle `None` voltage values in grid down scenarios - Fix for https://github.com/jasonacox/Powerwall-Dashboard/issues/683
     * Added `None` value handling in three-phase voltage calculations to prevent `TypeError` exceptions
     * Converts `None` voltage parameters to `0` before performing arithmetic operations
     * Prevents crashes when grid is down and voltage readings are unavailable
     * Added comprehensive unit tests to verify None handling behavior for all scenarios: grid down (all None), mixed None/valid values, and numeric-only values

## v0.14.8 - CLI Tool and PW3 Power Vitals Fix

* Add standalone `pypowerwall` command-line tool - installed automatically with pip
     * Added `entry_points` to `setup.py` to create console script
     * Refactored `__main__.py` to use a `main()` function as entry point
     * Users can now run `pypowerwall` command directly instead of `python -m pypowerwall`
     * Maintains backward compatibility - both methods work identically
     * Available commands: `pypowerwall scan`, `pypowerwall setup`, `pypowerwall fleetapi`, `pypowerwall get`, `pypowerwall set`, `pypowerwall version`
* Fix Powerwall 3 power output (PINV_Pout) in vitals for TEDAPI mode
     * Corrected signal source from `PCH_AcRealPowerAB` to `PCH_BatteryPower` for accurate per battery power reporting

## v0.14.7 - Reserve Level 0 Fix

* Fix bug where `pypowerwall set` command could not set battery reserve level to 0 - Fix by @ParaAdBellum in https://github.com/jasonacox/pypowerwall/pull/252
     * Changed default value for `-reserve` argument from `None` to `-1` (sentinel value)
     * Updated conditional checks to compare against `-1` instead of using truthiness evaluation
     * Previously, `not args.reserve` evaluated to `True` when reserve was set to 0, preventing the reserve from being set

## v0.14.6 - Firmware 25.42.2+ Support

* Add gzip decompression support for firmware 25.42.2+ TEDAPI responses - Fix by @bolagnaise in https://github.com/jasonacox/pypowerwall/pull/251
     * Gateway firmware 25.42.2 and later returns gzip-compressed responses for DIN and other TEDAPI endpoints
     * Added `decompress_response()` helper function to handle both compressed and uncompressed responses transparently
     * Updated all TEDAPI methods (`get_din()`, `get_config()`, `get_status()`, `get_device_controller()`, `get_firmware_version()`, `get_components()`, `get_battery_block()`) to decompress responses
     * Added error handling for UnicodeDecodeError in DIN decode operation to gracefully handle corrupted or invalid responses
     * Maintains backward compatibility with older firmware versions that return uncompressed responses

## v0.14.5 - Performance Improvements

* Performance Fixes and Improvements
     * Fix variable shadowing in `grid_status()` method: renamed `type` parameter to `output_type` to avoid shadowing Python's built-in `type()` function
     * Add backward compatibility for deprecated `type` parameter - still supported but `output_type` is now preferred
     * Fix return type annotation for `extract_grid_status()` method: changed from `str` to `Optional[str]` to accurately reflect function can return `None`
     * Add age and expiration logging to TEDAPI Components cache for debugging consistency
     * Proxy server build t86
* Rename incorrect unit test file (test_ prefix indicates unit tests) by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/226
* Simple reliability improvements by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/240
* Add aggregation unit tests by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/241
* Update all Python versions to be consistent by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/243
* Add CSV endpoint tests to the proxy by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/244
* Add csv/v2 endpoint unit tests by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/245

## v0.14.4 - Expansion Pack Energy Fix

* **Fix expansion pack energy data** by processing all BMS components in TEDAPI responses - Fix by @rlerdorf in https://github.com/jasonacox/pypowerwall/pull/239
* Refactored `get_pw3_vitals()` to process ALL BMS components and match them to batteries (main units and expansions) via HVP serial numbers
* Creates individual TEPOD entries in `/vitals` for each battery including expansion packs with accurate energy data
* Simplified `/pod` endpoint by removing complex subtraction-based energy calculation logic - expansion packs now appear automatically as TEPOD entries
* Refactored `get_blocks()` to retrieve expansion pack energy from vitals TEPOD entries instead of making separate API calls
* Improves data accuracy and reduces API calls by directly extracting expansion pack energy from parallel BMS/HVP component arrays
* Validated on system with 2 Powerwall 3 units (Leader + Follower) and 1 Expansion Pack showing correct energy values for all three batteries
* Proxy server build t85

## v0.14.3 - Battery Expansion and Grid Meter Support

* Add support for Powerwall 3 Battery Expansion Packs in TEDAPI mode - Fix for issue https://github.com/jasonacox/pypowerwall/issues/227 by @rlerdorf in https://github.com/jasonacox/pypowerwall/pull/236
* Battery expansions (battery-only units without inverters) now appear in `/pw/battery_blocks`, `/pod`, and `/tedapi/battery` endpoints
* The `get_blocks()` function now reads battery expansion data from the configuration's `battery_expansions` array and fetches BMS component data for each expansion unit
* Expansion units are identified with `"Type": "BatteryExpansion"` and include battery capacity metrics (`nominal_energy_remaining`, `nominal_full_pack_energy`)
* Inverter-related fields (`pinv_state`, `p_out`, `v_out`, etc.) are set to `None` for expansions since they don't have inverters
* The `/pod` endpoint calculates expansion pack energy by subtracting known battery values from system totals (individual expansion BMS data not exposed by Tesla)
* For multiple expansion packs, the first entry shows combined totals with "(combined)" suffix, while additional entries show `null` values
* Add support for TEMSA/MSA grid meter data in `/vitals` endpoint for Powerwall 3 systems
* PW3 MSA data fallback: reads from `components.msa` with signals array format conversion when `esCan.bus.MSA` is unavailable
* Voltage reference mapping: converts PW3 ground-referenced voltages (VL1G/VL2G/VL3G) to neutral-referenced (VL1N/VL2N/VL3N) for consistency
* TEMSA block in vitals now includes grid voltage, current, and instantaneous power readings for PW3 backup switches

## v0.14.2 - Misc

* Move API lock timeout messages in exponential backoff mechanism to DEBUG logging to prevent noise for regular users.

## v0.14.1 - Test Coverage & battery_blocks Fix

* Add unit tests expanding coverage: version parsing, core Powerwall methods (poll json output, power aggregation, grid_status numeric/json, alerts fallback path, set_operation validation, reserve/mode helpers, temps, site_name)
* Introduce stub client in tests for deterministic, offline execution
* Fix `battery_blocks()` KeyError when vitals include a battery serial not present in `/api/system_status` `battery_blocks` (create entry lazily)
* Harden battery temperature/state merge logic for mixed firmware/mode scenarios
* No public API changes


## v0.14.0 - Fix for TeslaPy and FleetAPI

* Pin and embed TeslaPy code patch directly into pyPowerwall to help address issue setting Powerwall Mode - see https://github.com/jasonacox/pypowerwall/issues/197
* FleetAPI CLI: improved error handling, skips incomplete sites, clearer output to help address issue where token can't be refreshed due to missing energy_site_id key - see https://github.com/jasonacox/pypowerwall/issues/198

## v0.13.2 - TEDAPI Lock Optimization

* Fix TEDAPI lock contention issues causing "Timeout for locked object" errors under concurrent load by optimizing cache-before-lock pattern in core functions
* Optimize `get_config()`, `get_status()`, `get_device_controller()`, `get_firmware_version()`, `get_components()`, and `get_battery_block()` to check cache before acquiring expensive locks
* Remove redundant API call in `pypowerwall_tedapi.py` `get_api_system_status()` method
* Fix proxy server KeyError when status response missing version or git_hash keys by using defensive key access
* Fix proxy server KeyError when auth dictionary missing AuthCookie or UserRecord keys in cookie mode
* Improve performance and reduce lock timeout errors in multi-threaded environments like the pypowerwall proxy server
* Enhance `compute_LL_voltage()` function with voltage threshold detection (100V) to better handle single-phase systems with residual voltages on inactive legs, as well as split- and three-phase systems.
* These optimizations benefit all methods that depend on the core TEDAPI functions, including `vitals()`, `get_blocks()`, and `get_battery_blocks()`

## v0.13.1 - TEDAPI Battery Blocks

* Fix missing battery_blocks data on PW3 with Multiple Powerwalls in Local Mode in https://github.com/jasonacox/pypowerwall/issues/131
* Fix errant API base URL check. by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/185
* Update TEDAPI to pull battery blocks from vitals for PW3 Systems by @jasonacox in https://github.com/jasonacox/pypowerwall/pull/184

## v0.13.0 - TEDAPI Updates

* Additional values /json endpoint by @erikgieseler in https://github.com/jasonacox/pypowerwall/pull/176
* Use Neurio for TEDAPI data when Tesla Remote Meter is not present by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/157
* Initial simple unit test by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/181
* Add connection pool to TEDAPI by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/177
* Add METER_Z (Backup Switch) data to vitals and aggregates data - See https://github.com/jasonacox/Powerwall-Dashboard/discussions/629#discussioncomment-13284217
* Update and add documentation helps: contributor, conduct and API (python and proxy)
* Fix logic for aggregates API for consolidated voltage and current data by @jasonacox in https://github.com/jasonacox/pypowerwall/pull/183

## v0.12.12 - Multiple PW3 Fix

* Bug Fix - Logic added in https://github.com/jasonacox/pypowerwall/pull/169 does not iterate through all PW3 strings. This adds logic to handle multiple PW3 string sets. Reported in https://github.com/jasonacox/pypowerwall/issues/172. 

## v0.12.11 - Error Handling

* Fix error handling in component data handling in TEDAPI.

## v0.12.10 - Power Flow and Other Fixes

* Add PROXY_BASE_URL option for reverse proxying by @mccahan in https://github.com/jasonacox/pypowerwall/pull/155
* Fix issue with power flow animation showing blank when opened more than once by @mccahan in https://github.com/jasonacox/pypowerwall/pull/156
* Add fan speed routes and update proxy version to t71 by @jasonacox in https://github.com/jasonacox/pypowerwall/pull/161
* Fix for
TypeError: PyPowerwallTEDAPI.vitals() got an unexpected keyword argument 'force' by @F1p in https://github.com/jasonacox/pypowerwall/pull/164
* Catch error condition when components payload is empty or malformed. Bug in extract_fan_speeds() reported by by @jgleigh in jasonacox/Powerwall-Dashboard#392 and https://github.com/jasonacox/pypowerwall/issues/167
* Issue #162: add /pw/XXX endpoints to expose Powerwall() API methods by @JohnJ9ml in https://github.com/jasonacox/pypowerwall/pull/166
* PW3 Vitals Fix - Switch from using device specific URI https://{GW_IP}/tedapi/device/{pw_din}/v1 to https://{GW_IP}/tedapi/v1 - Corrects 502 error condition on some Powerwall 3 systems by @johncuthbertuk in https://github.com/jasonacox/pypowerwall/pull/169

## v0.12.9 - Fan Speeds

* Add PVAC fan speeds to TEDAPI vitals monitoring (PVAC_Fan_Speed_Actual_RPM and PVAC_Fan_Speed_Target_RPM).

## v0.12.8 - TEDAPI Improvements

* Avoid divide by zero when nominalFullPackEnergyWh is zero by @rlpm in https://github.com/jasonacox/pypowerwall/pull/150
* Add thread locking to TEDAPI by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/148

## v0.12.7 - SystemConnectedToGrid Fix

* Alerts in extract_grid_status can be None. Block this edge case. #145

## v0.12.6 - Aggregates Data

* Updated aggregates call to include site current (METER_X) and external PV inverter data in solar (METER_Y). Reported in Issue #140.

## v0.12.5 - Normalize Alerts

* Fix an issue in TEDAPI where the grid status is not accurately reported in certain edge cases. Now, only the "SystemConnectedToGrid" alert will appear if it is present in alerts API. This update also eliminates the risk of duplicate and redundant ("SystemGridConnected") alerts and normalizes this specific alert. PR https://github.com/jasonacox/pypowerwall/pull/139 by @Nexarian

## v0.12.4 - Neurio Vitals

* Update proxy for /csv/v2 API support by @jasonacox in https://github.com/jasonacox/pypowerwall/pull/134
* Fix CTS data retrieval in TEDAPI vitals processor #136 by @jasonacox in https://github.com/jasonacox/pypowerwall/pull/137
* Fix bug in TEDAPI vitals processor that was not pulling in all Neurio CTS data. Issue reported in https://github.com/jasonacox/Powerwall-Dashboard/discussions/578#discussioncomment-12034018 and tracked in https://github.com/jasonacox/pypowerwall/issues/136.

## v0.12.3 - Custom GW IP

* Fix TEDAPI URL from constant GW_IP to constructor selectable host gw_ip by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/129 - The hard-coded 192.168.91.1 for the TEDAPI internal endpoint doesn't always work if you're using NAT. This change enables support for this use-case.
* See https://gist.github.com/jasonacox/91479957d0605248d7eadb919585616c?permalink_comment_id=5373785#gistcomment-5373785 for NAP implementation example.

## v0.12.2 - Cache Expiration Fix

* Fix bug in cache expiration timeout code that was not honoring pwcacheexpire setting. Raised by @erikgiesele in https://github.com/jasonacox/pypowerwall/issues/122 - PW_CACHE_EXPIRE=0 not possible? (Proxy)
* Add WARNING log in proxy for settings below 5s.
* Change TEDAPI config default timeout from 300s to 5s and link to pwcacheexpire setting.

## v0.12.1 - Scanner Update

* Large-scale refactor of scan function by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/117
     - Function `scan()` returns a list of the discovered devices for use as a utility function.
     - Ability to silence output for use as a utility.
     - Improve performance of multi-threaded scan by using a Queue.
     - General code flow improvements and encapsulation.
     - Add ability to work with standalone inverters.

```python
from pypowerwall.scan import scan
found_devices = scan(interactive = False)
```


## v0.12.0 - Add Controller Data

* TEDAPI: Add `get_device_controller()` to get device data which includes Powerwall THC_AmbientTemp data. Credit to @ygelfand for discovery and reported in https://github.com/jasonacox/Powerwall-Dashboard/discussions/392#discussioncomment-11360474
* Updated `vitals()` to include Powerwall temperature data. 
* Proxy Updated to t66 to include API response for /tedapi/controller.
* Remove Negative Solar Values [Option] by @jasonacox in https://github.com/jasonacox/pypowerwall/pull/113
* Solar-Only Cloud Access - Fix errors with site references by @Nexarian in https://github.com/jasonacox/pypowerwall/pull/115

## v0.11.1 - PW3 and FleetAPI Bugfix

* TEDAPI: Fix bug with activeAlerts logic causing errors on systems with multiple Powerwall 3's. Identified by @rmotapar in https://github.com/jasonacox/Powerwall-Dashboard/issues/387#issuecomment-2336431741 
* FleetAPI: Fix connect() to handle non-energy products in the getsites response. Identified by @gregrahn in https://github.com/jasonacox/pypowerwall/issues/111

## v0.11.0 - Add PW3 Vitals

* Add polling of Powerwall 3 Devices to pull in PW3 specific string data, capacity, voltages, frequencies, and alerts. 
* This creates mock TEPOD, PVAC and PVS compatible payloads available in vitals().

Proxy URLs updated for PW3:
* http://localhost:8675/vitals 
* http://localhost:8675/help (verify pw3 shows True) 
* http://localhost:8675/tedapi/components
* http://localhost:8675/tedapi/battery  

## v0.10.10 - Add Grid Control

* Add a function and command line options to allow user to get and set grid charging and exporting modes (see https://github.com/jasonacox/pypowerwall/issues/108).
* Supports FleetAPI and Cloud modes only (not Local mode)

#### Command Line Examples

```bash
# Connect to Cloud
python3 -m pypowerwall setup # or fleetapi

# Get Current Settings
python3 -m pypowerwall get

# Turn on Grid charging
python3 -m pypowerwall set -gridcharging on

# Turn off Grid charging
python3 -m pypowerwall  set -gridcharging off

# Set Grid Export to Solar (PV) energy only
python3 -m pypowerwall set -gridexport pv_only

# Set Grid Export to Battery and Solar energy
python3 -m pypowerwall set -gridexport battery_ok

# Disable export of all energy to grid
python3 -m pypowerwall set -gridexport never
```

#### Programming Examples

```python
import pypowerwall

# FleetAPI Mode
PW_HOST=""
PW_EMAIL="my@example.com"
pw = pypowerwall.Powerwall(host=PW_HOST, email=PW_EMAIL, fleetapi=True)

# Get modes
pw.get_grid_charging()
pw.get_grid_export()

# Set modes
pw.set_grid_charging("on") # set grid charging mode (on or off)
pw.set_grid_export("pv_only")   # set grid export mode (battery_ok, pv_only, or never)
```

## v0.10.9 - TEDAPI Voltage & Current

* Add computed voltage and current to `/api/meters/aggregates` from TEDAPI status data.
* Fix error in `num_meters_aggregated` calculation in aggregates.

## v0.10.8 - TEDAPI Firmware Version

* Add TEDAPI `get_firmware_version()` to poll Powerwall for firmware version. Discovered by @geptto in https://github.com/jasonacox/pypowerwall/issues/97. This function has been integrated into pypowerwall existing APIs (e.g. `pw.version()`)
* Add TEDAPI `get_components()` and `get_battery_block()` functions which providing additional Powerwall 3 related device vital information for Powerwall 3 owners. Discovered by @lignumaqua in https://github.com/jasonacox/Powerwall-Dashboard/discussions/392#discussioncomment-9864364. The plan it to integrate this data into the other device vitals payloads (TODO).

## v0.10.7 - Energy History

* FleetAPI - Add `get_history()` and `get_calendar_history()` to return energy, power, soe, and other history data.

```python
import pypowerwall

pw = pypowerwall.Powerwall(host=PW_HOST, email=PW_EMAIL, fleetapi=True)
pw.client.fleet.get_calendar_history(kind="soe")
pw.client.fleet.get_history(kind="power")
```

## v0.10.6 - pyLint Cleanup

* Minor Bug Fixes - TEDAPI get_reserve() fix to address unscaled results.
* pyLint Cleanup of Code

## v0.10.5 - Minor Fixes

* Fix for TEDAPI "full" (e.g. Powerwall 3) mode, including `grid_status` bug resulting in false reports of grid status, `level()` bug where data gap resulted in 0% state of charge and `alerts()` where data gap from tedapi resulted in a `null` alert.
* Add TEDAPI API call locking to limit load caused by concurrent polling.
* Proxy - Add battery full_pack and remaining energy data to `/pod` API call for all cases.

## v0.10.4 - Powerwall 3 Local API Support

* Add local support for Powerwall 3 using TEDAPI. 
* TEDAPI will activate in `hybrid` (using TEDAPI for vitals and existing local APIs for other metrics) or `full` (all data from TEDAPI) mode to provide better Powerwall 3 support.
* The `full` mode will automatically activate when the customer `password` is blank and `gw_pwd` is set.
* Note: The `full` mode will provide less metrics than `hybrid` mode since Powerwall 2/+ systems have additional APIs that are used in `hybrid` mode to fetch additional data

```python
import pypowerwall

# Activate HYBRID mode (for Powerwall / 2 / + systems)
pw = pypowerwall.Powerwall("192.168.91.1", password=PASSWORD, email=EMAIL, gw_pwd=PW_GW_PWD)

# Activate FULL mode (for all systems including Powerwall 3)
pw = pypowerwall.Powerwall("192.168.91.1", gw_pwd=PW_GW_PWD)
```

Related:
* #97 
* https://github.com/jasonacox/Powerwall-Dashboard/issues/387


## v0.10.3 - TEDAPI Connect Update

* Update `setup.py` to include dependencies on `protobuf>=3.20.0`.
* Add TEDAPI `connect()` logic to better validate Gateway endpoint access.
* Add documentation for TEDAPI setup.
* Update CLI to support TEDAPI calls.
* Proxy t60 - Fix edge case where `/csv` API will error due to NoneType inputs.
* Add TEDAPI argument to set custom GW IP address.

```bash
# Connect to TEDAPI and pull data
python3 -m pypowerwall tedapi

# Direct call to TEDAPI class test function (optional password)
python3 -m pypowerwall.tedapi GWPASSWORD
python3 -m pypowerwall.tedapi --debug
python3 -m pypowerwall.tedapi --gw_ip 192.168.91.1 --debug
```

## v0.10.2 - FleetAPI Hotfix

* Fix FleetAPI setup script as raised in https://github.com/jasonacox/pypowerwall/issues/98.
* Update FleetAPI documentation and CLI usage.

## v0.10.1 - TEDAPI Vitals Hotfix

* Fix PVAC lookup error logic in TEDAPI class vitals() function.
* Add alerts and other elements to PVAC TETHC TESYNC vitals.
* Update vitals Neurio block to include correct location and adjust RealPower based on power scale factor.

## v0.10.0 - New Device Vitals

* Add support for `/tedapi` API access on Gateway (requires connectivity to 192.168.91.1 GW and Gateway Password) with access to "config" and "status" data.
* Adds drop-in replacement for depreciated `/vitals` API and payload using the new TEDAPI class. This allows easy access to Powerwall device vitals.
* Proxy update to t58 to support TEDAPI with environmental variable `PW_GW_PWD` for Gateway Password. Also added FleetAPI, Cloud and TEDAPI specific GET calls, `/fleetapi`, `/cloud`, and `/tedapi` respectively.

```python
# How to Activate the TEDAPI Mode
import pypowerwall

gw_pwd = "GW_PASSWORD" # Gateway Passowrd usually on QR code on Gateway

host = "192.168.91.1" # Direct Connect to GW
pw = pypowerwall.Powerwall(host,password,email,timezone,gw_pwd=gw_pwd)
print(pw.vitals())
```

```python
# New TEDAPI Class
import pypowerwall.tedapi

tedapi = pypowerwall.tedapi.TEDAPI("GW_PASSWORD")

config = tedapi.get_config()
status = tedapi.get_status()

meterAggregates = status.get('control', {}).get('meterAggregates', [])
for meter in meterAggregates:
    location = meter.get('location', 'Unknown').title()
    realPowerW = int(meter.get('realPowerW', 0))
    print(f"   - {location}: {realPowerW}W")

```

## v0.9.1 - Bug Fixes and Updates

* Fix bug in time_remaining_hours() and convert print statements in FleetAPI to log messages.
* Fix CLI bug related to `site_id` as raised by @darroni in https://github.com/jasonacox/pypowerwall/issues/93
* Add CLI option for local mode to get status:

```bash
python -m pypowerwall get -host 10.1.2.3 -password 'myPassword'
```

## v0.9.0 - FleetAPI Support

* v0.9.0 - Tesla (official) FleetAPI cloud mode support by @jasonacox in https://github.com/jasonacox/pypowerwall/pull/91 - This adds the FleetAPI class and mapping for pypowerwall.
* FleetAPI setup provided by module CLI: `python -m pypowerwall fleetapi`
* Adds `auto_select` mode for instatiating a Powerwall connection: `local` mode, `fleetapi` mode and `cloud` mode. Provides `pw.mode` class variable as the mode selected.

```python
    import pypowerwall

    # Option 1 - LOCAL MODE - Credentials for your Powerwall - Customer Login
    password="password"
    email="email@example.com"
    host = "10.0.1.123"               # Address of your Powerwall Gateway
    timezone = "America/Los_Angeles"  # Your local timezone

    # Option 2 - FLEETAPI MODE - Requires Setup
    host = password = email = ""
    timezone = "America/Los_Angeles" 

    # Option 3 - CLOUD MODE - Requires Setup
    host = password = ""
    email='email@example.com'
    timezone = "America/Los_Angeles"
 
    # Connect to Powerwall - auto_select mode (local, fleetapi, cloud)
    pw = pypowerwall.Powerwall(host,password,email,timezone,auto_select=True)

    print(f"Connected to Powerwall with mode: {pw.mode}")
```

## v0.8.5 - Solar Only

* Fix bug with setup for certain Solar Only systems where setup process fails. Identified by @hulkster in https://github.com/jasonacox/Powerwall-Dashboard/discussions/475

## v0.8.4 - Set Reserve

* Updated `set_reserve(level)` logic to handle levels from 0 to 100. Identified by @spoonwzd in #85

## v0.8.3 - Error Handling

* Added additional error handling logic to clean up exceptions.
* Proxy: Added command APIs for setting backup reserve and operating mode.

## v0.8.2 - 503 Error Handling

* Added 5 minute cooldown for HTTP 503 Service Unavailable errors from API calls.
* Proxy: Added DISABLED API handling logic.

## v0.8.1 - Set battery reserve, operation mode

* Added `get_mode()`, `set_mode()`,`set_reserve()`,and `set_operation()` function to set battery operation mode and/or reserve level by @emptywee in https://github.com/jasonacox/pypowerwall/pull/78. Likely won't work in the local mode.
* Added basic validation for main class `__init__()` parameters (a.k.a. user input).
* Better handling of 401/403 errors from Powerwall in local mode.
* Handle 50x errors from Powerwall in local mode.
* Added Alerts for Grid Status `alerts()`.
* New command line functions (`set` and `get`):

```
usage: PyPowerwall [-h] {setup,scan,set,get,version} ...

PyPowerwall Module v0.8.1

options:
  -h, --help            show this help message and exit

commands (run <command> -h to see usage information):
  {setup,scan,set,get,version}
    setup               Setup Tesla Login for Cloud Mode access
    scan                Scan local network for Powerwall gateway
    set                 Set Powerwall Mode and Reserve Level
    get                 Get Powerwall Settings and Power Levels
    version             Print version information
```

## v0.8.0 - Refactoring

* Refactored pyPowerwall by @emptywee in https://github.com/jasonacox/pypowerwall/pull/77 including:
  * Moved Local and Cloud based operation code into respective modules, providing better abstraction and making it easier to maintain and extend going forward.
  * Made meaning of the `jsonformat` parameter consistent across all method calls (breaking API change).
  * Removed Python 2.7 support.
  * Cleaned up code and adopted a more pythoinc style.
* Fixed battery_blocks() for non-vitals systems.

## v0.7.12 - Cachefile, Alerts & Strings

* Added logic to pull string data from `/api/solar_powerwall` API if vitals data is not available by @jasonacox in #76.
* Added alerts from `/api/solar_powerwall` when vitals not present by @DerickJohnson in #75. The vitals API is not present in firmware versions > 23.44, this provides a workaround to get alerts.
* Allow customization of the cachefile location and name by @emptywee in #74 via `cachefile` parameter.

```python
# Example
import pypowerwall
pw = pypowerwall.Powerwall(
     host="10.1.2.30",
     password="secret",
     email="me@example.com",
     timezone="America/Los_Angeles",
     pwcacheexpire=5, 
     timeout=5, 
     poolmaxsize=10,
     cloudmode=False, 
     siteid=None, 
     authpath="", 
     authmode="cookie",
     cachefile=".powerwall",
     )
```

## v0.7.11 - Cooldown Mode

* Updated logic to disable vitals API calls for Firmware 23.44.0+
* Added rate limit detection and cooldown mode to allow Powerwall gateway time to recover.

## v0.7.10 - Cache 404 Responses

* Add cache and extended TTL for 404 responses from Powerwall as identified in issue https://github.com/jasonacox/Powerwall-Dashboard/issues/449. This will help reduce load on Powerwall gateway that may be causing rate limiting for some users (Firmware 23.44.0+).

## v0.7.9 - Cloud Grid Status

* Bug fix for correct grid status for Solar-Only systems on `cloud mode` (see https://github.com/jasonacox/Powerwall-Dashboard/issues/437)

## v0.7.8 - Cloud Fixes

* Fix enumeration of energy sites during `cloud mode` setup to handle incomplete sites with Unknown names or types by @dcgibbons in https://github.com/jasonacox/pypowerwall/pull/72 
* Proxy t41 Updates - Bug fixes for Solar-Only systems using `cloud mode` (see https://github.com/jasonacox/Powerwall-Dashboard/issues/437).

## v0.7.7 - Battery Data and Network Scanner

* Proxy t40: Use /api/system_status battery blocks data to augment /pod and /freq macro data APIs by @jasonacox in https://github.com/jasonacox/pypowerwall/pull/67 thanks to @ceeeekay in https://github.com/jasonacox/Powerwall-Dashboard/discussions/402#discussioncomment-8193776
* Network Scanner: Improve network scan speed by scanning multiple hosts simultaneously by @mcbirse in https://github.com/jasonacox/pypowerwall/pull/67. The number of hosts to scan simultaneously can be adjusted using the optional `-hosts=` argument (default = 30, maximum = 100), e.g. `python -m pypowerwall scan -hosts=50`

## v0.7.6 - 404 Bug Fix

* Fix Critical Bug - 404 HTTP Status Code Handling (Issue https://github.com/jasonacox/pypowerwall/issues/65).

## v0.7.5 - Cloud Mode Setup

* Added optional email address argument to Cloud Mode setup (`python -m pypowerwall setup -email=<email>`) by @mcbirse in https://github.com/jasonacox/pypowerwall/pull/64 to streamline Powerwall-Dashboard setup script.
* Updated network scanner output to advise Powerwall 3 is supported in Cloud Mode by @mcbirse in https://github.com/jasonacox/pypowerwall/pull/64

## v0.7.4 - Bearer Token Auth

pyPowerwall Updates
* This release adds the ability to use a Bearer Token for Authentication for the local Powerwall gateway API calls. This is selectable by defining `authmode='token'` in the initialization. The default mode uses the existing `AuthCookie` and `UserRecord` method.

```python
import pypowerwall

pw = pypowerwall.Powerwall(HOST, PASSWORD, EMAIL, TIMEZONE, authmode="token")
```

Proxy
* The above option is extended to the pyPowerwall Proxy via the environmental variable `PW_AUTH_MODE` set to cookie (default) or token.

Powerwall Network Scanner
* Added optional IP address argument to network scanner by @mcbirse in https://github.com/jasonacox/pypowerwall/pull/63. The Scan Function can now accept an additional argument `-ip=` to override the host IP address detection (`python -m pypowerwall scan -ip=192.168.1.100`). This may be useful where the host IP address/network cannot be detected correctly, for instance if pypowerwall is running inside a container.

## v0.7.3 - Cloud Mode Setup

* Setup will now check for `PW_AUTH_PATH` environmental variable to set the path for `.pypowerwall.auth` and `.pypowerwall.site` by @mcbirse in https://github.com/jasonacox/pypowerwall/pull/62
* Proxy t37 - Move signal handler to capture SIGTERM when proxy halts due to config error by @mcbirse in https://github.com/jasonacox/pypowerwall/pull/62. This ensures a containerized proxy will exit without delay when stopping or restarting the container.

## v0.7.2 - Cloud Auth Path

* Add pypowerwall setting to define path to cloud auth cache and site files in the initialization. It will default to current directory.
* Add pypowerwall setting to define energy site id in the initialization. It will default to None.

```python
import pypowerwall

pw = pypowerwall.Powerwall(email="email@example.com",cloudmode=True,siteid=1234567,authpath=".auth")
```

* Proxy will now use `PW_AUTH_PATH` as an environmental variable to set the path for `.pypowerwall.auth` and `.pypowerwall.site`.
* Proxy also has `PW_SITEID` as an environmental variable to set `siteid`.

## v0.7.1 - Tesla Cloud Mode

* Simulate Powerwall Energy Gateway via Tesla Cloud API calls. In `cloudmode` API calls to pypowerwall APIs will result in calls made to the Tesla API to fetch the data.

Cloud Mode Setup - Use pypowerwall to fetch your Tesla Owners API Token

```bash
python3 -m pypowerwall setup

# Token and site information stored in .pypowerwall.auth and .pypowerwall.site
```

Cloud Mode Code Example

```python
import pypowerwall
pw = pypowerwall.Powerwall(email="email@example.com",cloudmode=True)
pw.power()
# Output: {'site': 2977, 'solar': 1820, 'battery': -3860, 'load': 937}
pw.poll('/api/system_status/soe')
# Output: '{"percentage": 26.403205103271222}'
```

* Added new API function to compute estimated backup time remaining on the battery: `get_time_remaining()`

## v0.6.4 - Power Flow Animation

Proxy t29 Updates
* Default page rendered by proxy (http://pypowerwall:8675/) will render Powerflow Animation
* Animation assets (html, css, js, images, fonts, svg) will render from local filesystem instead of pulling from Powerwall TEG portal.
* Start prep for possible API removals from Powerwall TEG portal (see NOAPI settings)

Powerwall Network Scanner
* Adjust scan timeout default to 1,000ms (1s) to help with more consistent scans.

## v0.6.3 - Powerwall 3 Scan

* Added scan detection for new Powerwall 3 systems. API discovery is still underway so pypowerwall currently does not support Powerwall 3s. See https://github.com/jasonacox/Powerwall-Dashboard/issues/387

```
$ python3 -m pypowerwall scan

pyPowerwall Network Scanner [0.6.3]
Scan local network for Tesla Powerwall Gateways

    Your network appears to be: 10.0.1.0/24

    Enter Network or press enter to use 10.0.1.0/24: 

    Running Scan...
      Host: 10.0.1.2 ... OPEN - Not a Powerwall
      Host: 10.0.1.5 ... OPEN - Found Powerwall 3 [Currently Unsupported]
      Host: 10.0.1.8 ... OPEN - Not a Powerwall
      Host: 10.0.1.9 ... OPEN - Found Powerwall 3 [Currently Unsupported]
      Done                           

Discovered 2 Powerwall Gateway
     10.0.1.5 [Powerwall-3] Firmware Currently Unsupported - See https://tinyurl.com/pw3support
     10.0.1.9 [Powerwall-3] Firmware Currently Unsupported - See https://tinyurl.com/pw3support
```

## v0.6.2b - Proxy Grafana Support

* Proxy t28: Add a `grafana-dark` style for `PW_STYLE` settings to accommodate placing as iframe in newer Grafana versions (e.g. v9.4.14). See https://github.com/jasonacox/Powerwall-Dashboard/discussions/371.

## v0.6.2a - Proxy Graceful Exit

* Add alert PVS_a036_PvArcLockout by @JordanBelford in https://github.com/jasonacox/pypowerwall/pull/33
* Create `tessolarcharge.py` by @venturanc in https://github.com/jasonacox/pypowerwall/pull/36 &  https://github.com/jasonacox/pypowerwall/pull/37 & https://github.com/jasonacox/pypowerwall/pull/38
* Fix typos and spelling errors by @mcbirse in https://github.com/jasonacox/pypowerwall/pull/40
* Add alert definitions per #42 by @jasonacox in https://github.com/jasonacox/pypowerwall/pull/43
* Added two PVAC Alerts by @niabassey in https://github.com/jasonacox/pypowerwall/pull/46
* Added Firmware 23.28.1 to README.md by @niabassey in https://github.com/jasonacox/pypowerwall/pull/48
* Add proxy gracefully exit with SIGTERM by @rcasta74 in https://github.com/jasonacox/pypowerwall/pull/49

## v0.6.2 - Proxy Cache-Control

* PyPI 0.6.2
* Update docs for alerts by @DerickJohnson in https://github.com/jasonacox/pypowerwall/pull/29 and  https://github.com/jasonacox/pypowerwall/pull/30
* Fix Cache-Control no-cache header and allow for setting max-age, fixes #31 by @dkerr64 in https://github.com/jasonacox/pypowerwall/pull/32

## v0.6.1 - Add Grid Conditions

* PyPI 0.6.1
* Added new `SystemMicroGridFaulted` and `SystemWaitForUser` grid conditions to `grid_status()` function. Both are mapped to "DOWN" conditions. Discovery by @mcbrise in https://github.com/jasonacox/Powerwall-Dashboard/issues/158#issuecomment-1441648085.
* Revised error handling of SITE_DATA request due to issues noted in #12 when multiple sites are linked to the Tesla account by @mcbirse in https://github.com/jasonacox/pypowerwall/pull/25
* Proxy t24: Added new `/alerts/pw` endpoint with dictionary/object response format by @DerickJohnson in https://github.com/jasonacox/pypowerwall/pull/26

## v0.6.0 - Add Persistent HTTP Connections

* PyPI 0.6.0
* Added HTTP persistent connections for API requests to Powerwall Gateway by @mcbirse in https://github.com/jasonacox/pypowerwall/pull/21
* Requests to Gateway will now re-use persistent http connections which reduces load and increases response time.
* Uses default connection `poolmaxsize=10` to align with Session object defaults. Note: pool use applies to multi-threaded use of pyPowerwall only, e.g. as with the pyPowerwall Proxy Server.
* Added env `PW_POOL_MAXSIZE` to proxy server to allow this to be controlled (persistent connections disabled if set to zero).
* Added env `PW_TIMEOUT` to proxy server to allow timeout on requests to be adjusted.

## v0.5.1 - Fix grid_status() Off-Grid Map

* PyPI 0.5.1
* Add FreeBSD-specific installation instructions by @zi0r in https://github.com/jasonacox/pypowerwall/pull/18
* Add `grid_status()` responses for syncing to off-grid by @mcbirse in https://github.com/jasonacox/pypowerwall/pull/19

## v0.5.0 - Exception Handling for Powerwall Connection

* PyPI 0.5.0
* Added additional exception handling to help identify connection and login errors.
* Added `is_connected()` function to test for a successful connection to the Powerwall.
* Added firmware version to command line network scan (`python -m pypowerwall scan`)

[Proxy Server](https://github.com/jasonacox/pypowerwall/tree/main/proxy#pypowerwall-proxy-server) Updates (Build t16) - See [here](https://github.com/jasonacox/pypowerwall/blob/main/proxy/HELP.md#release-notes) for more Proxy Release notes.

* Add support for backup switch by @nhasan in https://github.com/jasonacox/pypowerwall/pull/12
* Add passthrough to Powerwall web interface and customize for iFrame displays by @danisla in https://github.com/jasonacox/pypowerwall/pull/14
* Remove scrollbars from web view by @danisla in https://github.com/jasonacox/pypowerwall/pull/15
* Add support for specifying a bind address by @zi0r in https://github.com/jasonacox/pypowerwall/pull/16
* Add shebang for direct execution by @zi0r in https://github.com/jasonacox/pypowerwall/pull/17

## v0.4.0 - Cache Bypass Option and New Functions

* PyPI 0.4.0
* Added parameter to `poll()` to force call (ignore cache)
* Added `alerts()` function to return an array of device alerts.
* Added `get_reserve()` function to return battery reserve setting.
* Added `grid_status()` function to return state of grid.
* Added `system_status()` function to return system status.
* Added `battery_blocks()` function to return battery specific information.
* Expanded class to include settings for cache expiration (`pwcacheexpire`) and connection `timeout`.

```python
# Force Poll
pw.poll('/api/system_status/soe',force=True)
'{"percentage":100}'

# Powerwall Alerts
pw.alerts()
['PodCommissionTime', 'GridCodesWrite', 'GridCodesWrite', 'FWUpdateSucceeded', 'THC_w155_Backup_Genealogy_Updated', 'PINV_a067_overvoltageNeutralChassis', 'THC_w155_Backup_Genealogy_Updated', 'PINV_a067_overvoltageNeutralChassis', 'PVS_a018_MciStringB', 'SYNC_a001_SW_App_Boot']

# Battery Reserve Setting
pw.get_reserve()
20.0

# State of Grid
pw.grid_status()
'UP'
```

## v0.3.0 - Device Vitals Alerts and Attributes

* PyPI 0.3.0
* Added alerts and additional attributes from `vitals()` output.
* Note: API change to `vitals()` output for dependant systems.

## v0.2.0 - Tesla Protocol Buffer Scheme Update

* PyPI 0.2.0
* Breaking change to Protobuf schema (PR #2) including:
* Files `tesla.proto` and `tesla_pb2.py`
* Impacted output from function `vitals()` and [examples/vitals.py](examples/vitals.py).

## v0.1.4 - Battery Level Percentage Scaling

* PyPI 0.1.4
* Changed "Network Scan" default timeout to 400ms for better detection.
* Added Tesla App style "Battery Level Percentage" Conversion option to `level()` to convert the level reading to the 95% scale used by the App. This converts the battery level percentage to be consistent with the Tesla App:

```python
>>> pw.level(scale=True)
39.971429212508326
>>> pw.level()
42.972857751882906
```

## v0.1.3 - Powerwall Temps

* PyPI 0.1.3
* Added `temp()` function to pull Powerwall temperatures.

```python
pw.temps(jsonformat=True)
```

```json
{
    "TETHC--2012170-25-E--TGxxxxxxxxxxxx": 17.5,
    "TETHC--3012170-05-B--TGxxxxxxxxxxxx": 17.700000000000003
}
```

## v0.1.2 - Error Handling and Proxy Stats

* PyPI 0.1.2
* Added better Error handling for calls to Powerwall with debug info for timeout and connection errors.
* Added timestamp stats to pypowerwall proxy server.py (via URI /stats and /stats/clear)

pyPowerwall Debug
```
DEBUG:pypowerwall [0.1.2]

DEBUG:loaded auth from cache file .powerwall
DEBUG:Starting new HTTPS connection (1): 10.0.1.2:443
DEBUG:ERROR Timeout waiting for Powerwall API https://10.0.1.2/api/devices/vitals
```

Proxy Stats
```json
{"pypowerwall": "0.1.2", "gets": 2, "errors": 3, "uri": {"/stats": 1, "/soe": 1}, "ts": 1641148636, "start": 1641148618, "clear": 1641148618}
```

## v0.1.1 - New System Info Functions

* PyPI 0.1.1
* Added stats to pypowerwall proxy server.py (via URI /stats and /stats/clear)
* Added Information Functions: `site_name()`, `version()`, `din()`, `uptime()`, and `status()`.

```python
     # Display System Info
     print("Site Name: %s - Firmware: %s - DIN: %s" % (pw.site_name(), pw.version(), pw.din()))
     print("System Uptime: %s\n" % pw.uptime())
```

## v0.1.0 - Vitals Data

* PyPI 0.1.0
* Added *protobuf* handling to support decoding the Powerwall Device Vitals data (requires protobuf package)
* Added function `vitals()` to pull Powerwall Device Vitals
* Added function `strings()` to pull data on solar panel strings (Voltage, Current, Power and State)

```python
     vitals = pw.vitals(jsonformat=False)
     strings = pw.strings(jsonformat=False, verbose=False)
```

## v0.0.3 - Binary Poll Function, Proxy Server and Simulator

* PyPI 0.0.3
* Added Proxy Server - Useful for metrics gathering tools like telegraf (see [proxy](proxy/)]).
* Added Powerwall Simulator - Mimics Powerwall Gateway responses for testing (see [pwsimulator](pwsimulator/)])
* Added raw binary poll capability to be able to pull *protobuf* formatted payloads like '/api/devices/vitals'.

```python
     payload = pw.poll('/api/devices/vitals')
```

## v0.0.2 - Scan Function

* PyPI 0.0.2
* pyPowerwall now has a network scan function to find the IP address of Powerwalls
```bash
# Scan Network for Powerwalls
python -m pypowerwall scan
```
Output Example:
```
pyPowerwall Network Scanner [0.0.2]
Scan local network for Tesla Powerwall Gateways

    Your network appears to be: 10.0.3.0/24

    Enter Network or press enter to use 10.0.3.0/24: 

    Running Scan...
      Host: 10.0.3.22 ... OPEN - Not a Powerwall
      Host: 10.0.3.45 ... OPEN - Found Powerwall 1234567-00-E--TG123456789ABC
      Done                           

Discovered 1 Powerwall Gateway
     10.0.1.45 [1234567-00-E--TG123456789ABC]
```

## v0.0.1 - Initial Release

* PyPI 0.0.1
* Initial Beta Release 0.0.1
