(window.webpackJsonp = window.webpackJsonp || []).push([
    [39],
    {
        1083: function (e, t, i) {
            "use strict";
            var r;
            Object.defineProperty(t, "__esModule", { value: !0 }),
                (t.GRID_CODES_MODAL = t.GRID_CODE_FILTER_FREQUENCY_WARNING = t.GRIDCODE_ALL_OTHER_SELECTION = t.GRIDCODE_ALL_OTHER_STAR = t.gridCodeNestedLookupKeys = t.GridCodesNestedLookupKey = void 0),
                (function (e) {
                    (e.country = "country"), (e.state = "state"), (e.distributor = "distributor"), (e.utility = "utility"), (e.retailer = "retailer"), (e.region = "region"), (e.grid_code = "grid_code");
                })((r = t.GridCodesNestedLookupKey || (t.GridCodesNestedLookupKey = {}))),
                (t.gridCodeNestedLookupKeys = [r.country, r.state, r.distributor, r.utility, r.retailer, r.region, r.grid_code]),
                (t.GRIDCODE_ALL_OTHER_STAR = "*"),
                (t.GRIDCODE_ALL_OTHER_SELECTION = "All Other"),
                (t.GRID_CODE_FILTER_FREQUENCY_WARNING = "GRID_CODE_FILTER_FREQUENCY_WARNING"),
                (t.GRID_CODES_MODAL = "GRID_CODES_MODAL");
        },
        1085: function (e, t, i) {
            "use strict";
            Object.defineProperty(t, "__esModule", { value: !0 }),
                (t.emptyGridCodeSelection = t.gridCodeToOption = t.gridCodeConfigToSelections = t.configValueToDropdownSelection = t.dropdownSelectionToConfigValue = t.shouldAutoSelect = t.shouldCollapse = t.resolveNestedLookupStructureBySelections = t.selectSubObject = t.subObjectHasValidGridCodes = t.gridCodePointsToInputs = t.applyGridCodePointsToOverrides = t.applyGridCodeOverridesToPoints = t.parseGridCodeNameForSettings = t.gridCodeSelectionsEqual = t.parseCSVRecordIntoGridCodeConfig = t.serializeGridCodeConfigIntoCSVRecord = t.parseCSVRecordIntoArray = t.parseRegionsCSVIntoNestedLookupStructure = void 0);
            const r = i(1083),
                n = i(134),
                o = i(1086);
            function d(e) {
                let t = [""],
                    i = !1;
                for (let r = 0; r < e.length; r++) {
                    const n = e[r];
                    '"' !== n ? ("," !== n || i ? (t[t.length - 1] += n) : t.push("")) : (i = !i);
                }
                return t;
            }
            function _(e) {
                if (!e) return null;
                const t = e.split("_");
                if (t.length < 4) return null;
                const [i, r, o] = t,
                    d = parseFloat(i),
                    _ = parseFloat(r);
                if (isNaN(d) || isNaN(_)) return null;
                let s;
                switch (o) {
                    case "1":
                        s = n.PhaseType.SINGLE;
                        break;
                    case "2":
                        s = n.PhaseType.TWO;
                        break;
                    case "3":
                        s = n.PhaseType.THREE;
                        break;
                    case "s":
                        s = n.PhaseType.SPLIT;
                        break;
                    case "WyeLL":
                        s = n.PhaseType.WYE_LL;
                        break;
                    default:
                        return null;
                }
                return { grid_code: e, grid_freq_setting: d, grid_voltage_setting: _, grid_phase_setting: s };
            }
            function s(e, t) {
                return "string" != typeof t || Array.isArray(e) ? null : e[t];
            }
            (t.parseRegionsCSVIntoNestedLookupStructure = function (e, t) {
                let i = {};
                return (
                    e
                        .split("\n")
                        .slice(1)
                        .forEach((e) => {
                            const r = d(e);
                            if (r.length < 6) return;
                            let n,
                                [o, s, a, l, u, c, g] = r;
                            i[s] || (i[s] = {}),
                                i[s][a] || (i[s][a] = {}),
                                i[s][a][l] || (i[s][a][l] = {}),
                                i[s][a][l][u] || (i[s][a][l][u] = {}),
                                i[s][a][l][u][c] || (i[s][a][l][u][c] = {}),
                                i[s][a][l][u][c][g] || (i[s][a][l][u][c][g] = []),
                                (n = t ? t[o] : _(o)),
                                n && i[s][a][l][u][c][g].push(n);
                        }),
                    i
                );
            }),
                (t.parseCSVRecordIntoArray = d),
                (t.serializeGridCodeConfigIntoCSVRecord = function (e) {
                    var t, i, r, n, o, d, _;
                    return [
                        null !== (t = e.grid_code) && void 0 !== t ? t : "",
                        null !== (i = e.country) && void 0 !== i ? i : "",
                        null !== (r = e.state) && void 0 !== r ? r : "",
                        null !== (n = e.distributor) && void 0 !== n ? n : "",
                        null !== (o = e.utility) && void 0 !== o ? o : "",
                        null !== (d = e.retailer) && void 0 !== d ? d : "",
                        null !== (_ = e.region) && void 0 !== _ ? _ : "",
                    ]
                        .map((e) => (e.includes(",") ? `"${e}"` : e))
                        .join(",");
                }),
                (t.parseCSVRecordIntoGridCodeConfig = function (e) {
                    if (!e) return {};
                    const [t, i, r, n, o, _, s] = d(e);
                    return { grid_code: t || void 0, country: i || void 0, state: r || void 0, distributor: n || void 0, utility: o || void 0, retailer: _ || void 0, region: s || void 0 };
                }),
                (t.gridCodeSelectionsEqual = function (e, t) {
                    for (let i of r.gridCodeNestedLookupKeys) if (e[i] !== t[i]) return !1;
                    return !0;
                }),
                (t.parseGridCodeNameForSettings = _),
                (t.applyGridCodeOverridesToPoints = function (e, t) {
                    let i = null != t ? t : [];
                    return (null != e ? e : []).map((e) => {
                        const t = i.find((t) => t.name === e.name);
                        return Object.assign(Object.assign({}, e), { override: t ? t.value : null, value: t ? t.value : e.file_value });
                    });
                }),
                (t.applyGridCodePointsToOverrides = function (e, t) {
                    let i = null != e ? e : [];
                    const r = (null != t ? t : []).filter((e) => !i.find((t) => t.name === e.name));
                    return i.reduce((e, t) => ("number" == typeof t.override && e.push({ name: t.name, value: t.override }), e), r);
                }),
                (t.gridCodePointsToInputs = function (e) {
                    const t = {};
                    return (null != e ? e : []).forEach((e) => (t[e.name] = "number" == typeof e.override ? e.override.toString() : "")), t;
                }),
                (t.subObjectHasValidGridCodes = function e(t, i) {
                    if (Array.isArray(t)) {
                        for (let e of t) if (i(e)) return !0;
                        return !1;
                    }
                    for (let r in t) if (e(t[r], i)) return !0;
                    return !1;
                }),
                (t.selectSubObject = s),
                (t.resolveNestedLookupStructureBySelections = function (e, t, i) {
                    let n = e;
                    for (let e of r.gridCodeNestedLookupKeys) {
                        if (e === i) break;
                        let r = s(n, t[e]);
                        if (!r) return null;
                        n = r;
                    }
                    return n;
                }),
                (t.shouldCollapse = function (e) {
                    return !e.length || (1 === e.length && e[0] === r.GRIDCODE_ALL_OTHER_SELECTION);
                }),
                (t.shouldAutoSelect = function (e) {
                    return 1 === e.length;
                }),
                (t.dropdownSelectionToConfigValue = function (e) {
                    return e === r.GRIDCODE_ALL_OTHER_SELECTION ? r.GRIDCODE_ALL_OTHER_STAR : e;
                }),
                (t.configValueToDropdownSelection = function (e) {
                    return e === r.GRIDCODE_ALL_OTHER_STAR ? r.GRIDCODE_ALL_OTHER_SELECTION : e;
                }),
                (t.gridCodeConfigToSelections = function (e) {
                    return { country: e.country, state: e.state, distributor: e.distributor, utility: e.utility, retailer: e.retailer, region: e.region, grid_code: e.grid_code };
                }),
                (t.gridCodeToOption = function (e, t) {
                    const i = _(t);
                    return i ? { value: t, label: (0, o.formatGridCodeSettingsSummary)(e, i) } : null;
                }),
                (t.emptyGridCodeSelection = {
                    [r.GridCodesNestedLookupKey.country]: void 0,
                    [r.GridCodesNestedLookupKey.state]: void 0,
                    [r.GridCodesNestedLookupKey.distributor]: void 0,
                    [r.GridCodesNestedLookupKey.utility]: void 0,
                    [r.GridCodesNestedLookupKey.retailer]: void 0,
                    [r.GridCodesNestedLookupKey.region]: void 0,
                    [r.GridCodesNestedLookupKey.grid_code]: void 0,
                });
        },
        1086: function (e, t, i) {
            "use strict";
            Object.defineProperty(t, "__esModule", { value: !0 }), (t.gridCodePointMessages = t.gridCodeUnitMessages = t.gridCodeLevelMessages = t.formatGridCodeSettingsSummary = t.gridCodeViewMessages = void 0);
            const r = i(3),
                n = i(1083),
                o = i(577);
            (t.gridCodeViewMessages = (0, r.defineMessages)({
                filterFreqWarning: { id: "grid_code_view_filter_freq_warning", defaultMessage: "Carefully select the appropriate grid code to ensure that the system will run at the intended voltage and frequency." },
                settingsSummary: {
                    id: "grid_code_view_settings_summary",
                    description: "Provides a summary of the grid code settings: the voltage, frequency, and phase configuration (e.g. Split-Phase, Three-Phase, etc.)",
                    defaultMessage: "{voltage} {frequency} {phase}",
                },
                preconfigured: {
                    id: "grid_code_view_preconfigured_label",
                    description: "Label for a preconfigured grid code (the grid code is present in config but cannot be resolved using the lookup keys)",
                    defaultMessage: "PRECONFIGURED GRID CODE",
                },
            })),
                (t.formatGridCodeSettingsSummary = function (e, i) {
                    let r = "";
                    "number" == typeof i.grid_freq_setting && (r = e.formatMessage(o.unitMessages.hertz, { frequency: i.grid_freq_setting }));
                    let n = "";
                    "number" == typeof i.grid_voltage_setting && (n = e.formatMessage(o.unitMessages.volts, { voltage: i.grid_voltage_setting }));
                    const d = o.phaseMessages[i.grid_phase_setting];
                    let _ = d ? e.formatMessage(d) : "";
                    return e.formatMessage(t.gridCodeViewMessages.settingsSummary, { frequency: r, voltage: n, phase: _ });
                }),
                (t.gridCodeLevelMessages = (0, r.defineMessages)({
                    [n.GridCodesNestedLookupKey.country]: { id: "grid_code_view_country_label", defaultMessage: "COUNTRY" },
                    [n.GridCodesNestedLookupKey.distributor]: { id: "grid_code_view_distributor_label", defaultMessage: "DNO" },
                    [n.GridCodesNestedLookupKey.utility]: { id: "grid_code_view_utility_label", defaultMessage: "UTILITY" },
                    [n.GridCodesNestedLookupKey.retailer]: { id: "grid_code_view_retailer_label", defaultMessage: "RETAILER" },
                    [n.GridCodesNestedLookupKey.state]: { id: "grid_code_view_region_label", defaultMessage: "REGION" },
                    [n.GridCodesNestedLookupKey.region]: { id: "grid_code_view_standard_label", defaultMessage: "STANDARD" },
                    [n.GridCodesNestedLookupKey.grid_code]: { id: "grid_code_view_volt_freq_label", defaultMessage: "VOLTAGE/FREQUENCY" },
                })),
                (t.gridCodeUnitMessages = (0, r.defineMessages)({
                    grid_code_unit_Hz: { id: "grid_code_unit_Hz", defaultMessage: "Hz" },
                    grid_code_unit_s: { id: "grid_code_unit_s", defaultMessage: "seconds" },
                    grid_code_unit_V: { id: "grid_code_unit_V", defaultMessage: "Volts" },
                    grid_code_unit_V_pu: { id: "grid_code_unit_V_pu", defaultMessage: "V / V_nominal" },
                    grid_code_unit_enum: { id: "grid_code_unit_enum", defaultMessage: "enumerated value, see manual" },
                    grid_code_unit_bool: { id: "grid_code_unit_bool", defaultMessage: "0 = no, 1 = yes" },
                })),
                (t.gridCodePointMessages = (0, r.defineMessages)({
                    grid_code_point_nominal_grid_frequency: { id: "grid_code_point_nominal_grid_frequency", defaultMessage: "Nominal Grid Frequency" },
                    grid_code_point_nominal_grid_voltage: { id: "grid_code_point_nominal_grid_voltage", defaultMessage: " Nominal Grid Voltage (L-N)" },
                    grid_code_point_nominal_pinv_voltage: { id: "grid_code_point_nominal_pinv_voltage", defaultMessage: "Nominal Grid Voltage of connected Powerwalls" },
                    grid_code_point_vf_limit_under_voltage_0_grid_following: { id: "grid_code_point_vf_limit_under_voltage_0_grid_following", defaultMessage: "Under Voltage Reconnect Limit" },
                    grid_code_point_vf_limit_under_frequency_0_grid_following: { id: "grid_code_point_vf_limit_under_frequency_0_grid_following", defaultMessage: "Under Frequency Reconnect Limit" },
                    grid_code_point_vf_limit_under_voltage_1_grid_following: { id: "grid_code_point_vf_limit_under_voltage_1_grid_following", defaultMessage: "Under Voltage Trip 1 - Limit" },
                    grid_code_point_vf_limit_under_frequency_1_grid_following: { id: "grid_code_point_vf_limit_under_frequency_1_grid_following", defaultMessage: "Under Frequency Trip 1 - Limit" },
                    grid_code_point_vf_timing_under_voltage_1_grid_following: { id: "grid_code_point_vf_timing_under_voltage_1_grid_following", defaultMessage: "Under Voltage Trip 1 - Timing" },
                    grid_code_point_vf_timing_under_frequency_1_grid_following: { id: "grid_code_point_vf_timing_under_frequency_1_grid_following", defaultMessage: "Under Frequency Trip 1 - Timing" },
                    grid_code_point_vf_limit_over_voltage_0_grid_following: { id: "grid_code_point_vf_limit_over_voltage_0_grid_following", defaultMessage: "Over Voltage Reconnect Limit" },
                    grid_code_point_vf_limit_over_frequency_0_grid_following: { id: "grid_code_point_vf_limit_over_frequency_0_grid_following", defaultMessage: "Over Frequency Reconnect Limit" },
                    grid_code_point_vf_limit_over_voltage_1_grid_following: { id: "grid_code_point_vf_limit_over_voltage_1_grid_following", defaultMessage: "Over Voltage Trip 1 - Limit" },
                    grid_code_point_vf_limit_over_frequency_1_grid_following: { id: "grid_code_point_vf_limit_over_frequency_1_grid_following", defaultMessage: "Over Frequency Trip 1 - Limit" },
                    grid_code_point_vf_timing_over_voltage_1_grid_following: { id: "grid_code_point_vf_timing_over_voltage_1_grid_following", defaultMessage: "Over Voltage Trip 1 - Timing" },
                    grid_code_point_vf_timing_over_frequency_1_grid_following: { id: "grid_code_point_vf_timing_over_frequency_1_grid_following", defaultMessage: "Over Frequency Trip 1 - Timing" },
                    grid_code_point_vf_timing_qualifying_time_grid_following: { id: "grid_code_point_vf_timing_qualifying_time_grid_following", defaultMessage: "Inverter Grid Requalification time" },
                    grid_code_point_vf_param_allow_charging_while_qualifying: { id: "grid_code_point_vf_param_allow_charging_while_qualifying", defaultMessage: "Allow battery charging during grid qualification period" },
                    grid_code_point_PINVrx_SmartInvSelect: { id: "grid_code_point_PINVrx_SmartInvSelect", defaultMessage: "Enabled Smart Inverter Features" },
                }));
        },
        1089: function (e, t, i) {
            "use strict";
            i.r(t),
                i.d(t, "default", function () {
                    return a;
                });
            var r = i(2),
                n = i(1085);
            function o(e, t) {
                var i = Object.keys(e);
                if (Object.getOwnPropertySymbols) {
                    var r = Object.getOwnPropertySymbols(e);
                    t &&
                        (r = r.filter(function (t) {
                            return Object.getOwnPropertyDescriptor(e, t).enumerable;
                        })),
                        i.push.apply(i, r);
                }
                return i;
            }
            function d(e) {
                for (var t = 1; t < arguments.length; t++) {
                    var i = null != arguments[t] ? arguments[t] : {};
                    t % 2
                        ? o(Object(i), !0).forEach(function (t) {
                              _(e, t, i[t]);
                          })
                        : Object.getOwnPropertyDescriptors
                        ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(i))
                        : o(Object(i)).forEach(function (t) {
                              Object.defineProperty(e, t, Object.getOwnPropertyDescriptor(i, t));
                          });
                }
                return e;
            }
            function _(e, t, i) {
                return t in e ? Object.defineProperty(e, t, { value: i, enumerable: !0, configurable: !0, writable: !0 }) : (e[t] = i), e;
            }
            const s = {
                isRetrieving: !1,
                isFetching: !1,
                isSaving: !1,
                isSetting: !1,
                didInvalidate: !1,
                error: null,
                codes: {},
                config: {
                    country: void 0,
                    state: void 0,
                    distributor: void 0,
                    utility: void 0,
                    retailer: void 0,
                    region: void 0,
                    grid_code: void 0,
                    show_all_grid_codes: !1,
                    grid_code_overrides: [],
                    grid_voltage_setting: void 0,
                    grid_phase_setting: void 0,
                    grid_freq_setting: void 0,
                },
                status: null,
                servicesActive: !1,
                offGrid: !1,
                measuredFrequency: null,
            };
            function a(e = s, t) {
                switch (t.type) {
                    case r.REQUEST_SITE_INFO:
                        return d(d({}, e), {}, { isRetrieving: !0, didInvalidate: !1 });
                    case r.REQUEST_GRID_CODES:
                        return d(d({}, e), {}, { isFetching: !0, didInvalidate: !1 });
                    case r.REQUEST_SAVE_OFF_GRID:
                        return d(d({}, e), {}, { isSaving: !0, didInvalidate: !1 });
                    case r.REQUEST_SAVE_GRID_CODE:
                        return d(d({}, e), {}, { isSaving: !0, isSetting: t.isSetting, didInvalidate: !1 });
                    case r.RECEIVE_SITE_INFO_SUCCESS:
                        return d(d(d({}, e), l(e, t)), {}, { isRetrieving: !1, didInvalidate: !1 });
                    case r.RECEIVE_GRID_CODES_SUCCESS:
                        let i = t.gridRegions;
                        return d(d({}, e), {}, { isFetching: !1, didInvalidate: !1, codes: Object(n.parseRegionsCSVIntoNestedLookupStructure)(i.regions, i.grid_code_settings) });
                    case r.RECEIVE_SAVE_GRID_CODE_SUCCESS:
                        return d(d({}, e), {}, { isSaving: !1, didInvalidate: !1, lastUpdatedAt: t.receivedAt }, l(e, t));
                    case r.RECEIVE_SAVE_OFF_GRID_SUCCESS:
                        return d(d({}, e), {}, { isSaving: !1, didInvalidate: !1, offGrid: t.offGrid });
                    case r.RECEIVE_GRID_STATUS_SUCCESS:
                        return d(d({}, e), {}, { status: t.grid_status, servicesActive: t.grid_services_active });
                    case r.RECEIVE_SITE_INFO_ERROR:
                        return d(d({}, e), {}, { isRetrieving: !1, didInvalidate: !0 });
                    case r.RECEIVE_GRID_CODES_ERROR:
                        return d(d({}, e), {}, { isFetching: !1, didInvalidate: !0 });
                    case r.RECEIVE_SAVE_GRID_CODE_ERROR:
                    case r.RECEIVE_SAVE_OFF_GRID_ERROR:
                        return d(d({}, e), {}, { isSaving: !1, didInvalidate: !0 });
                    case r.RESET_ALL:
                    case r.RESET_GRID_CODE_CONFIG:
                        return s;
                    default:
                        return e;
                }
            }
            function l(e, t) {
                let i = d(d({}, e), {}, { offGrid: null != t.offgrid ? t.offgrid : e.offGrid, measuredFrequency: null != t.measured_frequency ? t.measured_frequency : e.measuredFrequency }),
                    r = t.grid_code;
                return r ? d(d({}, i), {}, { config: r }) : i;
            }
        },
        1096: function (e, t, i) {
            "use strict";
            i.r(t),
                i.d(t, "default", function () {
                    return a;
                });
            var r = i(2),
                n = i(93);
            function o(e, t) {
                var i = Object.keys(e);
                if (Object.getOwnPropertySymbols) {
                    var r = Object.getOwnPropertySymbols(e);
                    t &&
                        (r = r.filter(function (t) {
                            return Object.getOwnPropertyDescriptor(e, t).enumerable;
                        })),
                        i.push.apply(i, r);
                }
                return i;
            }
            function d(e) {
                for (var t = 1; t < arguments.length; t++) {
                    var i = null != arguments[t] ? arguments[t] : {};
                    t % 2
                        ? o(Object(i), !0).forEach(function (t) {
                              _(e, t, i[t]);
                          })
                        : Object.getOwnPropertyDescriptors
                        ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(i))
                        : o(Object(i)).forEach(function (t) {
                              Object.defineProperty(e, t, Object.getOwnPropertyDescriptor(i, t));
                          });
                }
                return e;
            }
            function _(e, t, i) {
                return t in e ? Object.defineProperty(e, t, { value: i, enumerable: !0, configurable: !0, writable: !0 }) : (e[t] = i), e;
            }
            const s = {
                isFetching: !1,
                isSaving: !1,
                didInvalidate: !1,
                siteName: "",
                timezone: null,
                mode: null,
                backupReserve: null,
                exportLimit: null,
                generationLimit: null,
                solarLimit: null,
                batteryLimit: null,
                hecoCommittedDischargePower: null,
                hecoFromHour: null,
                hecoFromMinute: null,
                hecoScheduledDispatchEnabled: null,
                hecoAlreadySet: null,
            };
            function a(e = s, t) {
                switch (t.type) {
                    case r.REQUEST_SITE_NAME:
                    case r.REQUEST_SITE_INFO:
                    case r.REQUEST_OPERATION_SETTINGS:
                    case r.REQUEST_TIMEZONE:
                        return d(d({}, e), {}, { isFetching: !0, didInvalidate: !1 });
                    case r.REQUEST_SAVE_SITE_NAME:
                    case r.REQUEST_SAVE_EXPORT_MODE:
                    case r.REQUEST_SAVE_OPERATION_SETTINGS:
                    case r.REQUEST_SAVE_TIMEZONE:
                        return d(d({}, e), {}, { isSaving: !0, didInvalidate: !1 });
                    case r.RECEIVE_SITE_NAME_SUCCESS:
                    case r.RECEIVE_SITE_INFO_SUCCESS:
                        const i = t.payload || t;
                        return d(d({}, e), {}, { isFetching: !1, didInvalidate: !1, lastUpdatedAt: t.receivedAt, siteName: i.site_name, timezone: i.timezone, netMeterMode: i.net_meter_mode });
                    case r.RECEIVE_SAVE_SITE_NAME_SUCCESS:
                        return d(d({}, e), {}, { isFetching: !1, didInvalidate: !1, lastUpdatedAt: t.receivedAt, siteName: t.siteName });
                    case r.RECEIVE_OPERATION_SETTINGS_SUCCESS:
                        return d(d({}, e), {}, { isFetching: !1, didInvalidate: !1, lastUpdatedAt: t.receivedAt }, l(e, t));
                    case r.RECEIVE_SAVE_OPERATION_SETTINGS_SUCCESS:
                        return d(d({}, e), {}, { isSaving: !1, didInvalidate: !1, lastSavedAt: t.receivedAt }, l(e, t));
                    case r.RECEIVE_TIMEZONE_SUCCESS:
                        return d(d({}, e), {}, { isFetching: !1, didInvalidate: !1, timezone: t.time_zone || e.timezone });
                    case r.RECEIVE_SAVE_TIMEZONE_SUCCESS:
                        return d(d({}, e), {}, { isSaving: !1, didInvalidate: !1, lastUpdatedAt: t.receivedAt, timezone: t.timezone });
                    case r.RECEIVE_GET_EXTRA_PROGRAMS_SUCCESS:
                        return d(
                            d({}, e),
                            {},
                            { isSaving: !1, didInvalidate: !1 },
                            (function (e, t) {
                                let i = (t.extraPrograms || []).find((e) => e.name === n.b.HECO && e.type === n.c.POWER_RANGE);
                                if (i && i.recurring_events.length > 0)
                                    return {
                                        hecoScheduledDispatchEnabled: !0,
                                        hecoCommittedDischargePower: 1e3 * i.recurring_events[0].discharge_power_kw[0],
                                        hecoFromHour: i.recurring_events[0].schedule.fromHour,
                                        hecoFromMinute: i.recurring_events[0].schedule.fromMinute,
                                        hecoAlreadySet: !0,
                                    };
                                return { hecoScheduledDispatchEnabled: !1, hecoAlreadySet: !1 };
                            })(0, t)
                        );
                    case r.RECEIVE_POST_EXTRA_PROGRAM_SUCCESS:
                        return d(d({}, e), {}, { isSaving: !1, didInvalidate: !1 });
                    case r.RECEIVE_SITEMASTER_SETTINGS_ERROR:
                    case r.RECEIVE_START_SITEMASTER_ERROR:
                    case r.RECEIVE_STOP_SITEMASTER_ERROR:
                    case r.RECEIVE_SITE_INFO_ERROR:
                    case r.RECEIVE_OPERATION_SETTINGS_ERROR:
                    case r.RECEIVE_TIMEZONE_ERROR:
                    case r.RECEIVE_GET_EXTRA_PROGRAMS_ERROR:
                    case r.RECEIVE_POST_EXTRA_PROGRAM_ERROR:
                        return d(d({}, e), {}, { isFetching: !1, didInvalidate: !0 });
                    case r.RECEIVE_SAVE_SITE_NAME_ERROR:
                    case r.RECEIVE_SAVE_OPERATION_SETTINGS_ERROR:
                    case r.RECEIVE_SAVE_TIMEZONE_ERROR:
                        return d(d({}, e), {}, { isSaving: !1, didInvalidate: !0 });
                    case r.RESET_ALL:
                    case r.RESET_OPERATION_SETTINGS:
                        return s;
                    default:
                        return e;
                }
            }
            function l(e, t) {
                let i = null != t.backup_reserve_percent ? t.backup_reserve_percent : t.backupReserve,
                    r = null != t.max_pv_export_power_kW ? t.max_pv_export_power_kW : t.solarLimit;
                return (
                    n.g.includes(t.mode) || (i = null),
                    {
                        mode: t.mode || e.mode,
                        backupReserve: null != i ? i : e.backupReserve,
                        exportLimit: null != i ? 100 - i : e.backupReserve,
                        solarLimit: void 0 !== r ? r : e.solarLimit,
                        generationLimit: null != t.generationLimit ? t.generationLimit : e.generationLimit,
                        batteryLimit: null != t.batteryLimit ? t.batteryLimit : e.batteryLimit,
                    }
                );
            }
        },
        1116: function (e, t, i) {
            "use strict";
            i.r(t),
                i.d(t, "default", function () {
                    return l;
                });
            var r = i(27),
                n = i(2);
            function o(e, t) {
                var i = Object.keys(e);
                if (Object.getOwnPropertySymbols) {
                    var r = Object.getOwnPropertySymbols(e);
                    t &&
                        (r = r.filter(function (t) {
                            return Object.getOwnPropertyDescriptor(e, t).enumerable;
                        })),
                        i.push.apply(i, r);
                }
                return i;
            }
            function d(e) {
                for (var t = 1; t < arguments.length; t++) {
                    var i = null != arguments[t] ? arguments[t] : {};
                    t % 2
                        ? o(Object(i), !0).forEach(function (t) {
                              _(e, t, i[t]);
                          })
                        : Object.getOwnPropertyDescriptors
                        ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(i))
                        : o(Object(i)).forEach(function (t) {
                              Object.defineProperty(e, t, Object.getOwnPropertyDescriptor(i, t));
                          });
                }
                return e;
            }
            function _(e, t, i) {
                return t in e ? Object.defineProperty(e, t, { value: i, enumerable: !0, configurable: !0, writable: !0 }) : (e[t] = i), e;
            }
            const s = { id: 1, brand: "", model: "", powerRating: null, port: null, baudrate: null, ip: null, revenueGrade: null },
                a = { isFetching: !1, isSaving: !1, isConnecting: !1, didInvalidate: !1, brands: [], models: {}, items: [s] };
            function l(e = a, t) {
                switch (t.type) {
                    case n.ADD_SOLAR:
                        return d(d({}, e), {}, { items: [...e.items, d(d({}, s), {}, { id: t.id })] });
                    case n.REMOVE_SOLAR:
                        let i = e.items.filter((e, i) => t.index !== i);
                        return d(d({}, e), {}, { items: i.length ? i : a.items });
                    case n.RECEIVE_SOLAR_CONFIG_SUCCESS: {
                        let i = d({}, e);
                        return t.solars.length && (i.items = t.solars.map((e, t) => ({ brand: e.brand, model: e.model, id: t + 1, powerRating: e.power_rating_watts, ip: e.ip_address || null, revenueGrade: e.revenue_grade || null }))), i;
                    }
                    case n.RECEIVE_SOLAR_BRANDS_SUCCESS:
                        return d(d({}, e), {}, { brands: t.brands });
                    case n.RECEIVE_SOLAR_MODELS_SUCCESS:
                        return d(d({}, e), {}, { models: d(d({}, e.models), {}, { [t.brand]: t.models }) });
                    case n.REQUEST_SAVE_SOLAR_INVERTERS:
                    case n.REQUEST_DELETE_SOLAR_INVERTER:
                        return d(d({}, e), {}, { isSaving: !0, didInvalidate: !1 });
                    case n.RECEIVE_SAVE_SOLAR_INVERTER_SUCCESS:
                        let o = 0,
                            _ = Object(r.cloneDeep)(
                                e.items.find((e, i) => {
                                    let r = e.id === t.id;
                                    return r && (o = i), r;
                                })
                            );
                        return d(
                            d({}, e),
                            {},
                            {
                                items: [
                                    ...e.items.slice(0, o),
                                    d(d({}, _), {}, { brand: t.brand, model: t.model, powerRating: t.power_rating_watts, ip: t.ip_address || null, revenueGrade: t.revenue_grade || null }),
                                    ...e.items.slice(o + 1),
                                ],
                            }
                        );
                    case n.RECEIVE_SAVE_SOLAR_INVERTERS_SUCCESS:
                        return d(d({}, e), {}, { isSaving: !1, didInvalidate: !1, lastUpdatedAt: Date.now() });
                    case n.RECEIVE_DELETE_SOLAR_INVERTER_SUCCESS: {
                        let i = [...e.items.slice(0, t.index), ...e.items.slice(t.index + 1)];
                        return d(d({}, e), {}, { isSaving: !1, didInvalidate: !1, items: i.length ? i : a.items });
                    }
                    case n.RECEIVE_SAVE_SOLAR_INVERTERS_ERROR:
                    case n.RECEIVE_DELETE_SOLAR_INVERTER_ERROR:
                        return d(d({}, e), {}, { isSaving: !1, didInvalidate: !0 });
                    case n.REQUEST_CONNECT_SOLAR_INVERTER:
                        return d(d({}, e), {}, { isConnecting: !0, didInvalidate: !1 });
                    case n.RECEIVE_CONNECT_SOLAR_INVERTER_SUCCESS:
                        return d(
                            d({}, e),
                            {},
                            {
                                isConnecting: !1,
                                didInvalidate: !0,
                                items: [
                                    ...e.items.slice(0, t.index),
                                    d(d({}, e.items[t.index]), {}, { brand: t.brand, model: t.model, powerRating: t.power_rating_watts, ip: t.ip_address, revenueGrade: t.revenue_grade || null }),
                                    ...e.items.slice(t.index + 1),
                                ],
                            }
                        );
                    case n.RECEIVE_CONNECT_SOLAR_INVERTER_ERROR:
                        return d(d({}, e), {}, { isConnecting: !1, didInvalidate: !0 });
                    case n.RESET_ALL:
                    case n.RESET_SOLAR_CONFIG:
                        return a;
                    default:
                        return e;
                }
            }
        },
        1119: function (e, t, i) {
            "use strict";
            i.r(t),
                i.d(t, "default", function () {
                    return l;
                });
            var r = i(27),
                n = i(2),
                o = i(22);
            function d(e, t) {
                var i = Object.keys(e);
                if (Object.getOwnPropertySymbols) {
                    var r = Object.getOwnPropertySymbols(e);
                    t &&
                        (r = r.filter(function (t) {
                            return Object.getOwnPropertyDescriptor(e, t).enumerable;
                        })),
                        i.push.apply(i, r);
                }
                return i;
            }
            function _(e) {
                for (var t = 1; t < arguments.length; t++) {
                    var i = null != arguments[t] ? arguments[t] : {};
                    t % 2
                        ? d(Object(i), !0).forEach(function (t) {
                              s(e, t, i[t]);
                          })
                        : Object.getOwnPropertyDescriptors
                        ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(i))
                        : d(Object(i)).forEach(function (t) {
                              Object.defineProperty(e, t, Object.getOwnPropertyDescriptor(i, t));
                          });
                }
                return e;
            }
            function s(e, t, i) {
                return t in e ? Object.defineProperty(e, t, { value: i, enumerable: !0, configurable: !0, writable: !0 }) : (e[t] = i), e;
            }
            const a = { isFetching: !1, didInvalidate: !1, chargeTests: [], meterResults: [], inverterResults: [], running: !1, currentStatus: null, hysteresis: null, status: null, error: null, alerts: [] };
            function l(e = a, t) {
                switch (t.type) {
                    case n.REQUEST_RUN_INVERTER_TEST:
                        let i = Object(r.cloneDeep)(e.inverterResults);
                        for (let e = 0; e < i.length; e++) null != i[e].results && i[e].results[o.n.LAST_ERROR] && (i[e].results[o.n.LAST_ERROR] = null);
                        return _(_({}, e), {}, { error: null, inverterResults: i, isFetching: !0, didInvalidate: !1, currentStatus: null });
                    case n.REQUEST_TEST_RESULTS:
                    case n.REQUEST_TEST_ALERTS:
                    case n.REQUEST_CANCEL_TEST:
                        return _(_({}, e), {}, { isFetching: !0, didInvalidate: !1 });
                    case n.RECEIVE_TEST_RESULTS:
                        return _(
                            _({}, e),
                            {},
                            {
                                isFetching: !1,
                                didInvalidate: !1,
                                lastRetrievedAt: t.receivedAt,
                                chargeTests: t.charge_tests || e.chargeTests,
                                meterResults: t.meter_results || e.meterResults,
                                inverterResults: t.inverter_results || e.inverterResults,
                                running: t.running,
                                error: t.error,
                                hysteresis: t.hysteresis,
                                currentStatus: t.running ? t.status : e.currentStatus,
                                status: t.status,
                            }
                        );
                    case n.RECEIVE_RUN_INVERTER_TEST_SUCCESS:
                        return _(_({}, e), {}, { isFetching: !1, didInvalidate: !1, lastTestedAt: t.receivedAt, running: t.running, currentStatus: t.running ? t.status : e.currentStatus, status: t.status });
                    case n.RECEIVE_RUN_INVERTER_TEST_ERROR:
                    case n.RECEIVE_TEST_RESULTS_ERROR:
                        return _(_({}, e), {}, { isFetching: !1, didInvalidate: !0, error: t.error });
                    case n.RECEIVE_TEST_ALERTS_SUCCESS:
                        return _(_({}, e), {}, { isFetching: !1, didInvalidate: !1, alerts: t.alerts });
                    case n.RECEIVE_CANCEL_TEST_SUCCESS:
                        return _(_({}, e), {}, { isFetching: !1, didInvalidate: !1, running: !1, currentStatus: null, status: o.o.CANCELED });
                    case n.RECEIVE_TEST_ALERTS_ERROR:
                    case n.RECEIVE_CANCEL_TEST_ERROR:
                        return _(_({}, e), {}, { isFetching: !1, didInvalidate: !0 });
                    case n.RESET_ALL:
                    case n.RESET_TESTS:
                        return a;
                    default:
                        return e;
                }
            }
        },
    },
]);
