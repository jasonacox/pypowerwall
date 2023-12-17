(window.webpackJsonp = window.webpackJsonp || []).push([
    [1],
    {
        1154: function (e, t, r) {
            "use strict";
            r.r(t),
                r.d(t, "initialCurrentTransformer", function () {
                    return u;
                }),
                r.d(t, "initialCurrentTransformersState", function () {
                    return m;
                }),
                r.d(t, "default", function () {
                    return g;
                }),
                r.d(t, "hasSolarCurrentTransformersSelector", function () {
                    return f;
                });
            var i = r(27),
                s = r(18),
                n = r.n(s),
                a = r(2),
                c = r(12),
                E = r(8),
                l = r(37),
                o = r(151);
            function d(e, t) {
                var r = Object.keys(e);
                if (Object.getOwnPropertySymbols) {
                    var i = Object.getOwnPropertySymbols(e);
                    t &&
                        (i = i.filter(function (t) {
                            return Object.getOwnPropertyDescriptor(e, t).enumerable;
                        })),
                        r.push.apply(r, i);
                }
                return r;
            }
            function R(e) {
                for (var t = 1; t < arguments.length; t++) {
                    var r = null != arguments[t] ? arguments[t] : {};
                    t % 2
                        ? d(Object(r), !0).forEach(function (t) {
                              _(e, t, r[t]);
                          })
                        : Object.getOwnPropertyDescriptors
                        ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(r))
                        : d(Object(r)).forEach(function (t) {
                              Object.defineProperty(e, t, Object.getOwnPropertyDescriptor(r, t));
                          });
                }
                return e;
            }
            function _(e, t, r) {
                return t in e ? Object.defineProperty(e, t, { value: r, enumerable: !0, configurable: !0, writable: !0 }) : (e[t] = r), e;
            }
            const T = Object(i.values)(E.n),
                S = ["ampRating", "phaseSequence", "inverted"],
                u = {
                    id: 1,
                    connectionType: null,
                    isRevenueGradeSolarMeter: !1,
                    ampRating: null,
                    phaseSequence: null,
                    watts: null,
                    amps: null,
                    volts: null,
                    realPowerScaleFactor: 1,
                    reactivePower: null,
                    apparentPower: null,
                    powerFactor: null,
                    inverted: !1,
                },
                m = [R(R({}, u), {}, { id: 1 }), R(R({}, u), {}, { id: 2 }), R(R({}, u), {}, { id: 3 }), R(R({}, u), {}, { id: 4 })],
                p = { instant_power: 0, last_communication_time: null },
                C = {
                    isFetching: !1,
                    isCreating: !1,
                    isSetting: !1,
                    didInvalidate: !1,
                    inverterMeterReadings: { enabled: !1, isFetching: !1, didInvalidate: !1 },
                    items: [{ id: 1, connectionType: null, shortID: "", serial: "", macAddress: "", ipAddress: "", status: null, verified: !1, location: c.CurrentTransformerConnectionTypes.SITE, currentTransformers: m }],
                    readSerials: [],
                    synchrometerSettings: {
                        isFetching: !1,
                        didInvalidate: !1,
                        ctVoltageReferences: { ct1: c.SyncCTVoltageReferenceType.DEFAULT, ct2: c.SyncCTVoltageReferenceType.DEFAULT, ct3: c.SyncCTVoltageReferenceType.DEFAULT },
                        ctVoltageReferenceOptions: { ct1: [c.SyncCTVoltageReferenceType.PHASE1], ct2: [c.SyncCTVoltageReferenceType.PHASE2], ct3: [c.SyncCTVoltageReferenceType.PHASE3] },
                    },
                    aggregates: Object(i.reduce)(T, (e, t) => ((e[t] = R({}, p)), e), {}),
                };
            function g(e = C, t) {
                switch (t.type) {
                    case a.ADD_METER:
                        return R(R({}, e), {}, { items: [...e.items, R(R({}, C.items[0]), {}, { id: t.id })] });
                    case a.REMOVE_METER:
                        let r = e.items.filter((e) => e.id !== t.id);
                        return r.length || (r = [R(R({}, C.items[0]), {}, { id: t.id })]), R(R({}, e), {}, { items: r });
                    case a.REQUEST_METER_CONFIG:
                    case a.REQUEST_METER_AMP_RATINGS:
                    case a.REQUEST_DETECT_METER:
                    case a.REQUEST_DELETE_METER:
                    case a.REQUEST_DELETE_METER_CTS:
                    case a.REQUEST_COMMISSION_METER:
                    case a.REQUEST_METER_READINGS:
                    case a.REQUEST_METER_FLIP_CT:
                    case a.REQUEST_METER_AGGREGATES:
                        return R(R({}, e), {}, { isFetching: !0, didInvalidate: !1 });
                    case a.REQUEST_SET_METER_AMP_RATINGS:
                    case a.REQUEST_SET_METER_CTS:
                        return R(R({}, e), {}, { isSetting: !0, didInvalidate: !1 });
                    case a.REQUEST_CREATE_METER:
                        return R(R({}, e), {}, { isCreating: !0, didInvalidate: !1 });
                    case a.RECEIVE_CREATE_METER_SUCCESS:
                        let s = 0,
                            E = Object(i.cloneDeep)(e.items.find((e, r) => (e.id === t.id && (s = r), e.id === t.id)));
                        return (
                            (E.shortID = t.shortID),
                            (E.serial = t.serial),
                            (E.location = t.location),
                            t.macAddress && t.macAddress.match(l.c) && (E.macAddress = t.macAddress),
                            t.ipAddress && t.ipAddress.match(l.b) && (E.ipAddress = t.ipAddress),
                            (E.connectionType = t.connectionType),
                            (E.verified = !!t.connected),
                            (E.location = t.location),
                            R(R({}, e), {}, { isCreating: !1, items: [...e.items.slice(0, s), E, ...e.items.slice(s + 1)] })
                        );
                    case a.RECEIVE_DETECT_METER_SUCCESS:
                        let d = 0,
                            _ = Object(i.cloneDeep)(e.items.find((e, r) => (e.id === t.id && (d = r), e.id === t.id)));
                        return (_.verified = !0), (_.connectionType = c.ConnectionTypes.NEURIO_W1_WIRED), R(R({}, e), {}, { isFetching: !1, didInvalidate: !1, items: [...e.items.slice(0, d), _, ...e.items.slice(d + 1)] });
                    case a.RECEIVE_METER_CONFIG_SUCCESS:
                        return R(
                            R({}, e),
                            {},
                            {
                                isFetching: null != t.isFetching ? t.isFetching : e.isFetching,
                                didInvalidate: !1,
                                items: t.meters
                                    .sort((e, t) => {
                                        const r = e.type,
                                            i = t.type;
                                        if (null != r && null != i) {
                                            if (r < i) return -1;
                                            if (r > i) return 1;
                                        }
                                        return 0;
                                    })
                                    .map((t, r) => {
                                        let s = Object(o.y)({ connectionType: t.type }),
                                            n = t.type === c.ConnectionTypes.MSA,
                                            a = Object(o.q)({ connectionType: t.type }),
                                            E = Object(i.cloneDeep)(m);
                                        if (
                                            (Object(o.s)(t.type) &&
                                                E.forEach((e, t) => {
                                                    e.phaseSequence = c.NeurioOrderedPhaseSequences[t];
                                                }),
                                            s && E.splice(-1, 1),
                                            n && E.splice(-2, 2),
                                            a)
                                        ) {
                                            let e = Object(i.isEmpty)(t.cts) ? c.CurrentTransformerConnectionTypes.SITE : t.cts[0].type;
                                            E.forEach((t, r) => {
                                                E[r].connectionType = e;
                                            });
                                        }
                                        Array.isArray(t.cts) || (t.cts = []),
                                            t.cts.forEach((e, t) => {
                                                (s && t >= 3) ||
                                                    e.valid.forEach((t, r) => {
                                                        t &&
                                                            (!s || (s && r < 3)) &&
                                                            ((E[r].realPowerScaleFactor = null != e.real_power_scale_factor ? e.real_power_scale_factor : 1),
                                                            2 === Math.trunc(E[r].realPowerScaleFactor) && e.type === c.CurrentTransformerConnectionTypes.SOLAR
                                                                ? (E[r].connectionType = c.CurrentTransformerConnectionTypes.DOUBLED_SOLAR)
                                                                : (E[r].connectionType = e.type),
                                                            (E[r].isRevenueGradeSolarMeter = e.type === c.CurrentTransformerConnectionTypes.SOLAR_RGM),
                                                            (E[r].inverted = e.inverted[r]));
                                                    });
                                            });
                                        const d = t.mac && t.mac.match(l.c) ? t.mac : C.items[0].macAddress,
                                            _ = t.ip_address && t.ip_address.match(l.b) ? t.ip_address : C.items[0].ipAddress,
                                            T = Object(o.v)(t.type) && (e.items || []).find(({ serial: e, shortID: r }) => e === t.serial && r === t.short_id),
                                            S = (T && T.status) || c.Statuses.UNKNOWN;
                                        return R(
                                            R({}, C.items[0]),
                                            {},
                                            {
                                                id: r + 1,
                                                connectionType: t.type,
                                                location: t.location,
                                                shortID: t.short_id,
                                                serial: t.serial,
                                                macAddress: d,
                                                ipAddress: _,
                                                status: t.connected ? c.Statuses.SUCCESS_METER : S,
                                                verified: !!t.connected || s || a || n,
                                                currentTransformers: E,
                                            }
                                        );
                                    }),
                            }
                        );
                    case a.RECEIVE_DELETE_METER_SUCCESS:
                        let g = 0;
                        for (let r = 0; r < e.items.length; r++)
                            if (e.items[r].id === t.id) {
                                g = r;
                                break;
                            }
                        let f = [R(R({}, C.items[0]), {}, { id: t.id })];
                        return e.items.length > 1 && (f = [...e.items.slice(0, g), ...e.items.slice(g + 1)]), R(R({}, e), {}, { isFetching: !1, didInvalidate: !1, items: f });
                    case a.RECEIVE_METER_CONFIG_UPDATE:
                        let I = e.items.findIndex((e) => (t.serial ? e.serial === t.serial : t.ip_address ? e.ip_address === t.ip_address : e.id === t.id)),
                            O = Object(i.cloneDeep)(e.items[I]);
                        return !O || (Object(o.s)(O.connectionType) && t.serial !== O.serial)
                            ? R(R({}, e), {}, { isFetching: !1 })
                            : ((O.status = t.status),
                              t.serial && (O.serial = t.serial),
                              t.short_id && (O.shortID = t.short_id),
                              t.location && (O.location = t.location),
                              t.mac && t.mac.match(l.c) && (O.macAddress = t.mac),
                              t.ip_address && t.ip_address.match(l.b) && (O.ipAddress = t.ip_address),
                              t.location && (O.location = t.location),
                              R(R({}, e), {}, { isFetching: null != t.isFetching ? t.isFetching : e.isFetching, items: [...e.items.slice(0, I), O, ...e.items.slice(I + 1)] }));
                    case a.RECEIVE_COMMISSION_METER_UPDATE:
                        let h = 0,
                            A = Object(i.cloneDeep)(e.items.find((e, r) => (e.id === t.id && (h = r), e.id === t.id)));
                        return A
                            ? ((A.status = t.status),
                              t.short_id && (A.shortID = t.short_id),
                              t.serial && (A.serial = t.serial),
                              t.location && (A.location = t.location),
                              R(R({}, e), {}, { items: [...e.items.slice(0, h), A, ...e.items.slice(h + 1)] }))
                            : e;
                    case a.RECEIVE_COMMISSION_METER_SUCCESS:
                        let y = 0,
                            M = Object(i.cloneDeep)(e.items.find((e, r) => (e.id === t.id && (y = r), e.id === t.id)));
                        return M
                            ? ((M.verified = !!t.verified),
                              t.shortID && (M.shortID = t.shortID),
                              t.serial && (M.serial = t.serial),
                              t.macAddress && t.macAddress.match(l.c) && (M.macAddress = t.macAddress),
                              t.ipAddress && t.ipAddress.match(l.b) && (M.ipAddress = t.ipAddress),
                              t.location && (M.location = M.location),
                              (M.connectionType = t.connectionType),
                              (M.status = t.status),
                              (M.lastUpdatedAt = t.receivedAt),
                              R(R({}, e), {}, { isFetching: !1, didInvalidate: !1, items: [...e.items.slice(0, y), M, ...e.items.slice(y + 1)] }))
                            : e;
                    case a.RECEIVE_METER_AMP_RATINGS_SUCCESS:
                        let v = 0,
                            b = Object(i.cloneDeep)(e.items.find((e, r) => (e.serial === t.serial && (v = r), e.serial === t.serial)));
                        return (
                            t.ampRatings.length === m.length &&
                                t.ampRatings.forEach((e, t) => {
                                    let r = b.currentTransformers[t];
                                    r.ampRating !== e && (r.ampRating = e);
                                }),
                            R(R({}, e), {}, { items: [...e.items.slice(0, v), b, ...e.items.slice(v + 1)] })
                        );
                    case a.RECEIVE_SET_METER_AMP_RATINGS_SUCCESS:
                        let F = 0,
                            V = Object(i.cloneDeep)(e.items.find((e, r) => (e.serial === t.serial && (F = r), e.serial === t.serial)));
                        return (
                            t.ampRatings.length === m.length &&
                                t.ampRatings.forEach((e, t) => {
                                    let r = V.currentTransformers[t];
                                    r.ampRating !== e && (r.ampRating = e);
                                }),
                            R(R({}, e), {}, { isSetting: !1, didInvalidate: !1, items: [...e.items.slice(0, F), V, ...e.items.slice(F + 1)] })
                        );
                    case a.RECEIVE_SET_METER_CTS_SUCCESS:
                        let D = 0,
                            N = Object(i.cloneDeep)(e.items.find((e, r) => (e.serial === t.serial && (D = r), e.serial === t.serial)));
                        return (
                            N.currentTransformers.forEach((e) => {
                                if (t.ids.length && t.ids.includes(e.id)) (e.connectionType = t.connectionType), (e.realPowerScaleFactor = t.realPowerScaleFactor);
                                else if (Object(o.x)(e.connectionType, t.connectionType)) {
                                    const t = ["id", ...S];
                                    for (let r in e) t.includes(r) || (e[r] = u[r]);
                                }
                            }),
                            R(R({}, e), {}, { isSetting: null != t.isSetting && t.isSetting, didInvalidate: !1, items: [...e.items.slice(0, D), N, ...e.items.slice(D + 1)] })
                        );
                    case a.RECEIVE_DELETE_METER_CTS_SUCCESS:
                        let U = 0;
                        const j = Object(i.cloneDeep)(e.items.find((e, r) => (e.serial === t.serial && (U = r), e.serial === t.serial)));
                        let w = [];
                        return (
                            m.forEach((e, t) => {
                                (Object(o.y)(j) && t >= 3) || w.push(R(R({}, e), Object(i.pick)(j.currentTransformers[t], S)));
                            }),
                            (j.currentTransformers = w),
                            R(R({}, e), {}, { isFetching: !1, didInvalidate: !1, items: [...e.items.slice(0, U), j, ...e.items.slice(U + 1)] })
                        );
                    case a.RECEIVE_METER_READINGS_SUCCESS:
                        let P = e.items,
                            G = e.lastReadingUpdatedAt,
                            L = e.readSerials;
                        if (null != t.readings && !Object(i.isEmpty)(t.readings)) {
                            P = Object(i.cloneDeep)(e.items);
                            for (const e in t.readings) {
                                const r = P.find((t) => t.serial === e),
                                    s = !Object(i.isEmpty)(t.readings[e].error);
                                if (null != r && t.readings[e].data && t.readings[e].data.cts && t.readings[e].data.cts.length) {
                                    let i = 4;
                                    Object(o.y)(r) && (i = 3), r.connectionType === c.ConnectionTypes.MSA && (i = 2);
                                    t.readings[e].data.cts.forEach((e, t) => {
                                        if (null != r && !s && null != n()(e, (e) => e.ct) && e.ct >= 1 && e.ct <= i) {
                                            let t = e.p_W,
                                                i = e.v_V,
                                                s = e.q_VAR;
                                            null != t && (r.currentTransformers[e.ct - 1].watts = t),
                                                null != t &&
                                                    null != i &&
                                                    null != s &&
                                                    ((r.currentTransformers[e.ct - 1].amps = 0 !== i ? t / i : 0),
                                                    (r.currentTransformers[e.ct - 1].volts = i),
                                                    (r.currentTransformers[e.ct - 1].reactivePower = s),
                                                    (r.currentTransformers[e.ct - 1].apparentPower = Object(o.a)(t, s)),
                                                    (r.currentTransformers[e.ct - 1].powerFactor = Object(o.b)(t, s)));
                                        } else
                                            null != r &&
                                                0 === n()(e, (e) => e.ct) &&
                                                t < i &&
                                                (r.currentTransformers[t] = R(R({}, r.currentTransformers[t]), {}, { watts: null, amps: null, volts: null, reactivePower: null, apparentPower: null, powerFactor: null }));
                                    });
                                }
                            }
                            const r = Object.keys(t.readings);
                            Object(i.without)(e.readSerials, ...r).forEach((e) => {
                                const t = P.find((t) => t.serial === e);
                                null != t && (t.currentTransformers = t.currentTransformers.map((e) => R(R({}, e), {}, { watts: null, amps: null, volts: null, reactivePower: null, apparentPower: null, powerFactor: null })));
                            }),
                                (G = Date.now()),
                                (L = r);
                        }
                        return R(R({}, e), {}, { isFetching: !1, didInvalidate: !1, lastUpdatedAt: t.receivedAt, lastReadingUpdatedAt: G, readSerials: L, items: P });
                    case a.RECEIVE_METER_FLIP_CT_SUCCESS:
                        let Q = 0,
                            Y = Object(i.cloneDeep)(e.items.find((e, r) => (e.serial === t.serial && (Q = r), e.serial === t.serial)));
                        return (
                            t.inverted.length === m.length &&
                                t.inverted.forEach((e, t) => {
                                    if (Object(o.y)(Y) && t >= 3) return;
                                    let r = Y.currentTransformers[t];
                                    r.inverted !== e && ((r.inverted = e), null != r.amps && (r.amps *= -1), null != r.watts && (r.watts *= -1));
                                }),
                            R(R({}, e), {}, { isFetching: !1, didInvalidate: !1, items: [...e.items.slice(0, Q), Y, ...e.items.slice(Q + 1)] })
                        );
                    case a.RECEIVE_METER_AGGREGATES_SUCCESS:
                        return R(
                            R({}, e),
                            {},
                            {
                                isFetching: !1,
                                didInvalidate: !1,
                                lastUpdatedAt: t.receivedAt,
                                lastMeterReadingAt: Math.max(...Object(i.values)(t.aggregates).map((e) => (null != e.last_communication_time ? Date.parse(e.last_communication_time) : 0))),
                                aggregates: Object(i.reduce)(T, (r, i) => ((r[i] = R(R({}, e.aggregates[i]), n()(t, (e) => e.aggregates[i]) || p)), r), R({}, e.aggregates)),
                            }
                        );
                    case a.RECEIVE_METER_CONFIG_ERROR:
                    case a.RECEIVE_METER_AMP_RATINGS_ERROR:
                    case a.RECEIVE_DETECT_METER_ERROR:
                    case a.RECEIVE_DELETE_METER_ERROR:
                    case a.RECEIVE_DELETE_METER_CTS_ERROR:
                    case a.RECEIVE_COMMISSION_METER_ERROR:
                    case a.RECEIVE_METER_READINGS_ERROR:
                    case a.RECEIVE_METER_FLIP_CT_ERROR:
                    case a.RECEIVE_METER_AGGREGATES_ERROR:
                        return R(R({}, e), {}, { isFetching: !1, didInvalidate: !0 });
                    case a.RECEIVE_CREATE_METER_ERROR:
                        return R(R({}, e), {}, { isCreating: !1, didInvalidate: !0 });
                    case a.RECEIVE_SET_METER_AMP_RATINGS_ERROR:
                    case a.RECEIVE_SET_METER_CTS_ERROR:
                        return R(R({}, e), {}, { isSetting: !1, didInvalidate: !0 });
                    case a.RESET_METER_CURRENT_TRANSFORMER_READINGS:
                        let k = e.items;
                        return (
                            e.readSerials.length &&
                                ((k = Object(i.cloneDeep)(e.items)),
                                e.readSerials.forEach((e) => {
                                    const t = k.find((t) => t.serial === e);
                                    null != t && (t.currentTransformers = t.currentTransformers.map((e) => R(R({}, e), {}, { watts: null, amps: null, volts: null, reactivePower: null, apparentPower: null, powerFactor: null })));
                                })),
                            R(R({}, e), {}, { lastReadingUpdatedAt: null, items: k })
                        );
                    case a.REQUEST_SYNC_CT_VOLTAGE_REFERENCES:
                    case a.REQUEST_SET_SYNC_CT_VOLTAGE_REFERENCES:
                    case a.REQUEST_SYNC_CT_VOLTAGE_REFERENCE_OPTIONS:
                        return R(R({}, e), {}, { synchrometerSettings: R(R({}, e.synchrometerSettings), {}, { isFetching: !0, didInvalidate: !1 }) });
                    case a.RECEIVE_SYNC_CT_VOLTAGE_REFERENCES_SUCCESS:
                    case a.RECEIVE_SET_SYNC_CT_VOLTAGE_REFERENCES_SUCCESS:
                        return R(R({}, e), {}, { synchrometerSettings: R(R({}, e.synchrometerSettings), {}, { isFetching: !1, didInvalidate: !1, ctVoltageReferences: t.pairing }) });
                    case a.RECEIVE_SYNC_CT_VOLTAGE_REFERENCES_ERROR:
                    case a.RECEIVE_SET_SYNC_CT_VOLTAGE_REFERENCES_ERROR:
                    case a.RECEIVE_OPERATION_SETTINGS_ERROR:
                        return R(R({}, e), {}, { synchrometerSettings: R(R({}, e.synchrometerSettings), {}, { isFetching: !1, didInvalidate: !0 }) });
                    case a.RECEIVE_SYNC_CT_VOLTAGE_REFERENCE_OPTIONS_SUCCESS:
                        return R(R({}, e), {}, { synchrometerSettings: R(R({}, e.synchrometerSettings), {}, { isFetching: !1, didInvalidate: !1, ctVoltageReferenceOptions: t.options }) });
                    case a.REQUEST_ENABLE_INVERTER_METER_READINGS:
                        return R(R({}, e), {}, { inverterMeterReadings: { enabled: e.inverterMeterReadings.enabled, isFetching: !0, didInvalidate: !1 } });
                    case a.RECEIVE_ENABLE_INVERTER_METER_READINGS_SUCCESS:
                        return R(R({}, e), {}, { inverterMeterReadings: { enabled: t.enabled, isFetching: !1, didInvalidate: !1 } });
                    case a.RECEIVE_ENABLE_INVERTER_METER_READINGS_ERROR:
                        return R(R({}, e), {}, { inverterMeterReadings: { enabled: e.inverterMeterReadings.enabled, isFetching: !1, didInvalidate: !0 } });
                    case a.RESET_ALL:
                    case a.RESET_METER_CONFIG:
                        return C;
                    default:
                        return e;
                }
            }
            function f({ meter: e }) {
                return e.items.some((e) => Object(o.n)(e.currentTransformers));
            }
        },
    },
]);
