class PowerFlowVisualization extends React.Component {
    static getActiveIcons(props) {
        const { 
            activeTypes, 
            loadPower, 
            gridPower, 
            solarPower, 
            batteryPower, 
            gridStatus, 
            units, 
            precision, 
            showNegative, 
            correctNegative, 
            correctLoadPower 
        } = props;
        
        // If no active types, return empty array
        if (activeTypes.length === 0) return [];
        
        // Calculate display powers for each energy source/sink
        const displayPowers = PowerFlowVisualization.getDisplayPowers(
            loadPower, 
            solarPower, 
            batteryPower, 
            gridPower, 
            gridStatus, 
            units, 
            precision, 
            showNegative, 
            correctNegative, 
            correctLoadPower
        );
        
        // Filter active types based on power values
        const activeIcons = activeTypes.filter((type) => {
            switch (type) {
                case ENERGY_TYPES.SOLAR:
                    return displayPowers[ENERGY_TYPES.SOLAR] > 0 && displayPowers.adjusted > 0;
                case ENERGY_TYPES.BATTERY:
                    return displayPowers[ENERGY_TYPES.BATTERY] !== 0;
                case ENERGY_TYPES.GRID:
                    return gridStatus !== GRID_STATUS.ISLANDED && displayPowers[ENERGY_TYPES.GRID] !== 0;
                default:
                    return false;
            }
        });
        
        // Add usage icon if required conditions are met
        if (
            activeTypes.includes(ENERGY_TYPES.USAGE) && 
            loadPower != null && 
            ((correctLoadPower && formatNumber(displayPowers[ENERGY_TYPES.USAGE], precision) !== 0 && displayPowers[ENERGY_TYPES.USAGE] > 0) || 
             (!correctLoadPower && displayPowers[ENERGY_TYPES.USAGE] > 0))
        ) {
            activeIcons.push(ENERGY_TYPES.USAGE);
        }
        
        // If only one icon is active, return empty array (we need at least 2 for flow)
        return activeIcons.length === 1 ? [] : activeIcons;
    }
    
    static getDisplayPowers(loadPower, solarPower, batteryPower, gridPower, gridStatus, units, precision, showNegative, correctNegative, correctLoadPower) {
        const displayPowers = { 
            USAGE: 0, 
            SOLAR: 0, 
            BATTERY: 0, 
            GRID: 0,
            adjusted: 0 
        };
        
        // Process solar power
        if (solarPower != null) {
            displayPowers.adjusted = solarPower;
        }
        
        // Handle negative load power if correction is enabled
        if (loadPower != null && loadPower < 0 && correctNegative) {
            displayPowers.adjusted += Math.abs(loadPower);
        }
        
        // Calculate display values for each power source/sink
        displayPowers[ENERGY_TYPES.SOLAR] = PowerFlowVisualization.getDisplayValue(
            displayPowers.adjusted, units, precision, correctNegative, showNegative
        );
        
        displayPowers[ENERGY_TYPES.BATTERY] = PowerFlowVisualization.getDisplayValue(
            batteryPower, units, precision, false, showNegative
        );
        
        if (gridStatus !== GRID_STATUS.ISLANDED) {
            displayPowers[ENERGY_TYPES.GRID] = PowerFlowVisualization.getDisplayValue(
                gridPower, units, precision, false, showNegative
            );
        }
        
        // Calculate usage power based on whether correction is needed
        if (correctLoadPower) {
            // Calculate usage as sum of other power sources with proper sign
            displayPowers[ENERGY_TYPES.USAGE] += displayPowers[ENERGY_TYPES.SOLAR] * 
                (displayPowers.adjusted < 0 && !showNegative ? -1 : 1);
                
            displayPowers[ENERGY_TYPES.USAGE] += displayPowers[ENERGY_TYPES.BATTERY] * 
                (batteryPower != null && batteryPower < 0 && !showNegative ? -1 : 1);
                
            if (gridStatus !== GRID_STATUS.ISLANDED) {
                displayPowers[ENERGY_TYPES.USAGE] += displayPowers[ENERGY_TYPES.GRID] * 
                    (gridPower != null && gridPower < 0 && !showNegative ? -1 : 1);
            }
            
            // If negative and not showing negative, set to 0, otherwise format the number
            displayPowers[ENERGY_TYPES.USAGE] = displayPowers[ENERGY_TYPES.USAGE] < 0 && !showNegative 
                ? 0 
                : Number(formatNumber(displayPowers[ENERGY_TYPES.USAGE], precision));
        } else {
            // Direct display of load power
            displayPowers[ENERGY_TYPES.USAGE] = PowerFlowVisualization.getDisplayValue(
                loadPower, units, precision, correctNegative, showNegative
            );
        }
        
        return displayPowers;
    }
    
    static getDisplayValue(powerValue, units, precision, correctNegative = false, showNegative = false) {
        // Return 0 if power is null or negative and correction is enabled
        if (powerValue == null || (correctNegative && powerValue < 0)) {
            return 0;
        }
        
        const absolutePower = Math.abs(powerValue);
        
        // Only show power above the noise threshold
        if (absolutePower > CONSTANTS.METER_POWER_NOISE) {
            // Format the power value based on units and precision
            const formattedValue = formatPowerWithUnits(
                showNegative ? powerValue : absolutePower, 
                units, 
                precision
            );
            
            // Return just the numeric part, not the units
            return Number(formattedValue.split(" ")[0]);
        }
        
        return 0;
    }
    
    constructor(props) {
        super(props);
        
        // Bind event handlers
        this._handleSitemanagerStartStopClick = this._handleSitemanagerStartStopClick.bind(this);
        this._handleIslandingClick = this._handleIslandingClick.bind(this);
        
        // Initial state
        this.state = { 
            activeIcons: [], 
            colors: { 
                batteryToHome: COLORS.BATTERY, 
                batteryToGrid: COLORS.BATTERY, 
                gridToHome: COLORS.GRID, 
                gridToBattery: COLORS.GRID, 
                solarToBattery: COLORS.SOLAR, 
                solarToGrid: COLORS.SOLAR, 
                solarToHome: COLORS.SOLAR 
            } 
        };
    }
    
    // Initialize active icons when component mounts
    componentWillMount() {
        this.setState({ 
            activeIcons: PowerFlowVisualization.getActiveIcons(this.props) 
        });
    }
    
    // Update active icons when props change
    componentWillReceiveProps(nextProps) {
        this.setState({ 
            activeIcons: PowerFlowVisualization.getActiveIcons(nextProps) 
        });
    }
    
    render() {
        const {
            gridWidth,
            gridHeight,
            activeTypes,
            activeGlowRadius,
            indicatorRadius,
            indicatorGlowRadius,
            indicatorAnimationTimer,
            energyIconDiameter,
            energyIconBorderWidth,
            showPowerwall,
            showCompletePowerwall,
            sitemasterRunning,
            authenticated,
            lineSpacing,
            lineRadius,
            lineWidth,
            labelMargin,
            labelHeight,
            labelWidth,
            customLabels,
            iconStyle,
            iconContainerStyle,
            showLabels,
            handleInactiveLabelClick,
            handleNegativeLabelClick,
            showNegative,
            correctNegative,
            correctLoadPower,
            showZero,
            showIcons,
            inactiveColor,
            customIcons,
            availableTypes,
            units,
            precision,
            containerStyle,
            style,
            isResi,
            compact,
            criticalInstallationProblems,
        } = this.props;
        
        const { 
            batteryPower, 
            solarPower, 
            loadPower, 
            gridPower, 
            gridStatus, 
            gridServicesActive, 
            soe 
        } = this.props;
        
        const { activeIcons, colors } = this.state;
        
        // Check if no active types
        const noActiveTypes = activeTypes.length === 0;
        
        // Define grid center coordinates
        const gridCenterX = gridWidth / 2;
        const gridCenterY = gridHeight / 2;
        
        // Check which components are available and active
        const solarAvailable = availableTypes.includes(ENERGY_TYPES.SOLAR);
        const usageAvailable = availableTypes.includes(ENERGY_TYPES.USAGE);
        const gridAvailable = availableTypes.includes(ENERGY_TYPES.GRID);
        
        // Calculate display powers for the visualization
        const displayPowers = PowerFlowVisualization.getDisplayPowers(
            loadPower, 
            solarPower, 
            batteryPower, 
            gridPower, 
            gridStatus, 
            units, 
            precision, 
            showNegative, 
            correctNegative, 
            correctLoadPower
        );
        
        // Check which icons are active in current state
        const batteryActive = activeIcons.includes(ENERGY_TYPES.BATTERY);
        const usageActive = activeIcons.includes(ENERGY_TYPES.USAGE);
        const solarActive = activeIcons.includes(ENERGY_TYPES.SOLAR);
        const gridActive = activeIcons.includes(ENERGY_TYPES.GRID);
        
        // Set up power flow arrows between components
        // Battery to grid flow arrow
        const batteryToGridArrow = gridAvailable && batteryActive && 
            batteryPower > 0 && gridPower < 0 && 
            1000 * (displayPowers[ENERGY_TYPES.BATTERY] - displayPowers[ENERGY_TYPES.USAGE]) >= 
            PowerFlowVisualization.DISCHARGE_THRESHOLD
            ? (
                <use 
                    id="battery-to-grid" 
                    xlinkHref="#curvedArrow" 
                    stroke="url(#greenGrayGradient)" 
                    fill={colors.batteryToGrid} 
                    transform={`translate(${-1 * lineSpacing + gridWidth} ${gridCenterY / 2 + lineSpacing}) scale(-1 1)`} 
                />
            ) 
            : null;
        
        // Battery to home flow arrow
        const batteryToHomeArrow = usageAvailable && batteryActive && 
            usageActive && batteryPower > 0 
            ? (
                <use 
                    id="battery-to-home" 
                    xlinkHref="#curvedArrow" 
                    stroke="url(#greenBlueGradient)" 
                    fill={colors.batteryToHome} 
                    x={lineSpacing} 
                    y={gridCenterY / 2 + lineSpacing} 
                />
            ) 
            : null;
        
        // Grid to battery flow arrow
        const gridToBatteryArrow = gridAvailable && gridActive && 
            batteryActive && gridPower > 0 && batteryPower < 0 && 
            displayPowers[ENERGY_TYPES.GRID] > displayPowers[ENERGY_TYPES.USAGE]
            ? (
                <use 
                    id="grid-to-battery" 
                    xlinkHref="#curvedArrowMirror" 
                    stroke="url(#grayGreenGradient)" 
                    fill={colors.gridToBattery} 
                    x={-1 * lineSpacing} 
                    y={lineSpacing} 
                />
            ) 
            : null;
        
        // Solar to grid flow arrow
        const solarToGridArrow = solarAvailable && gridAvailable && 
            solarActive && gridActive && gridPower < 0
            ? (
                <use 
                    id="solar-to-grid" 
                    xlinkHref="#curvedArrow" 
                    stroke="url(#yellowGrayGradient)" 
                    fill={colors.solarToGrid} 
                    transform={`rotate(180 ${gridCenterX} ${gridCenterY})`} 
                    x={1 * lineSpacing} 
                    y={gridCenterY / 2 + lineSpacing} 
                />
            ) 
            : null;
        
        // Solar to home flow arrow
        const solarToHomeArrow = solarAvailable && usageAvailable && 
            solarActive && usageActive && displayPowers.adjusted > 0 &&
            !((displayPowers[ENERGY_TYPES.SOLAR] === displayPowers[ENERGY_TYPES.BATTERY] * (showNegative ? -1 : 1) && 
               displayPowers[ENERGY_TYPES.USAGE] === displayPowers[ENERGY_TYPES.GRID]) || 
              (displayPowers[ENERGY_TYPES.SOLAR] === displayPowers[ENERGY_TYPES.GRID] * (showNegative ? -1 : 1) && 
               displayPowers[ENERGY_TYPES.BATTERY] === displayPowers[ENERGY_TYPES.USAGE]))
            ? (
                <use 
                    id="solar-to-home" 
                    xlinkHref="#curvedArrow" 
                    stroke="url(#blueYellowGradient)" 
                    fill={colors.solarToHome} 
                    transform={`translate(${lineSpacing} ${0.75 * gridHeight + -1 * lineSpacing}) scale(1 -1)`} 
                />
            ) 
            : null;
        
        // Grid to home and solar to battery arrows
        let gridToHomeArrow = null;
        let solarToBatteryArrow = null;
        let batteryToLowerArrow = null;
        
        if (noActiveTypes) {
            // Show inactive arrows with dashed lines when no active types
            gridToHomeArrow = (
                <use 
                    id="grid-to-home-inactive" 
                    xlinkHref="#horizontalArrow" 
                    stroke="gray" 
                    strokeDasharray="2,4" 
                />
            );
            
            solarToBatteryArrow = (
                <use 
                    id="solar-to-battery-inactive" 
                    xlinkHref="#verticalArrow" 
                    stroke="gray" 
                    strokeDasharray="2,4" 
                />
            );
        } else {
            // Show active arrows based on power flow conditions
            gridToHomeArrow = gridAvailable && usageAvailable && 
                gridActive && usageActive && gridPower > 0 
                ? (
                    <use 
                        id="grid-to-home" 
                        xlinkHref="#horizontalArrow" 
                        stroke="url(#grayBlueGradient)" 
                        fill={colors.gridToHome} 
                    />
                ) 
                : null;
            
            solarToBatteryArrow = solarAvailable && solarActive && 
                batteryActive && displayPowers.adjusted > 0 && batteryPower < 0 
                ? (
                    <use 
                        id="solar-to-battery" 
                        xlinkHref="#verticalArrow" 
                        stroke="url(#yellowGreenGradient)" 
                        fill={colors.solarToBattery} 
                    />
                ) 
                : null;
        }
        
        // Set indicator radius based on active state
        const activeIndicatorRadius = noActiveTypes ? 0 : indicatorRadius;
        const activeIndicatorGlowRadius = noActiveTypes ? 0 : indicatorGlowRadius;
        
        // Create empty icon placeholder
        const emptyIconPlaceholder = (
            <div 
                data-testid="7edf03b3-a222-4ebe-b757-5a4af34484bc" 
                style={{ 
                    width: energyIconDiameter + 2 * energyIconBorderWidth, 
                    height: energyIconDiameter + 2 * energyIconBorderWidth 
                }} 
            />
        );
        
        // Create icons for each component
        const solarIcon = showIcons 
            ? (
                <EnergyIcon
                    type={ENERGY_TYPES.SOLAR}
                    active={solarActive}
                    iconSize={energyIconDiameter}
                    borderWidth={energyIconBorderWidth}
                    showIconImage={customIcons && customIcons[ENERGY_TYPES.SOLAR] == null}
                    innerIconView={customIcons ? customIcons[ENERGY_TYPES.SOLAR] : null}
                    inactiveColor={inactiveColor}
                    iconStyle={iconStyle}
                    iconContainerStyle={{
                        ...iconContainerStyle,
                        borderColor: COLORS.SOLAR
                    }}
                />
            ) 
            : emptyIconPlaceholder;
        
        const gridIcon = showIcons 
            ? (
                <EnergyIcon
                    type={ENERGY_TYPES.GRID}
                    active={gridActive}
                    iconSize={energyIconDiameter}
                    borderWidth={energyIconBorderWidth}
                    showIconImage={customIcons && customIcons[ENERGY_TYPES.GRID] == null}
                    innerIconView={customIcons ? customIcons[ENERGY_TYPES.GRID] : null}
                    inactiveColor={inactiveColor}
                    iconStyle={iconStyle}
                    iconContainerStyle={{
                        ...iconContainerStyle,
                        borderColor: COLORS.GRID
                    }}
                />
            ) 
            : emptyIconPlaceholder;
        
        const usageIcon = showIcons 
            ? (
                <EnergyIcon
                    type={ENERGY_TYPES.USAGE}
                    active={usageActive}
                    iconSize={energyIconDiameter}
                    borderWidth={energyIconBorderWidth}
                    showIconImage={customIcons && customIcons[ENERGY_TYPES.USAGE] == null}
                    innerIconView={customIcons ? customIcons[ENERGY_TYPES.USAGE] : null}
                    inactiveColor={inactiveColor}
                    iconStyle={iconStyle}
                    iconContainerStyle={{
                        ...iconContainerStyle,
                        borderColor: COLORS.USAGE
                    }}
                />
            ) 
            : emptyIconPlaceholder;
        
        // Define indicator circle attributes
        const indicatorCircleAttrs = { 
            cx: 0, 
            cy: 0, 
            r: activeIndicatorRadius, 
            strokeOpacity: 0 
        };
        
        const indicatorGlowCircleAttrs = { 
            cx: 0, 
            cy: 0, 
            r: activeIndicatorGlowRadius, 
            fillOpacity: 0.2, 
            strokeOpacity: 0 
        };
        
        // Create inactive path elements for when no active types
        const inactiveSolarVerticalPath = noActiveTypes && 
            (solarAvailable || (gridAvailable && usageAvailable)) 
            ? (
                <g stroke={COLORS.INACTIVE} strokeWidth={lineWidth} fill="none">
                    <use xlinkHref={solarAvailable ? "#verticalPath" : "#halfVerticalPath"} />
                </g>
            ) 
            : null;
        
        const inactiveGridHorizontalPath = noActiveTypes && 
            gridAvailable && usageAvailable 
            ? (
                <g stroke={COLORS.INACTIVE} strokeWidth={lineWidth} fill="none">
                    <use xlinkHref="#horizontalPath" />
                </g>
            ) 
            : null;
        
        // Set container class name with appropriate modifiers
        let containerClassAttrs = { 
            className: this._getPowerFlowGridClassName(
                showCompletePowerwall, 
                sitemasterRunning, 
                authenticated, 
                gridServicesActive
            ) 
        };
        
        if (containerStyle != null) {
            containerClassAttrs.style = containerStyle;
        }
        
        // Add battery discharge indicator if needed
        if (!showIcons && !noActiveTypes && batteryPower != null && batteryPower !== 0) {
            batteryToLowerArrow = (
                <use 
                    xlinkHref="#halfVerticalArrow" 
                    stroke={COLORS.BATTERY} 
                    fill={COLORS.BATTERY} 
                />
            );
        }
        
        // Create powerwall component or battery icon
        const powerwallOrBatteryComponent = showPowerwall
            ? this._getPowerwall(
                showCompletePowerwall, 
                energyIconDiameter, 
                energyIconBorderWidth, 
                iconStyle, 
                soe, 
                sitemasterRunning, 
                noActiveTypes, 
                isResi
            )
            : (
                <div 
                    data-testid="c52444f1-a739-4789-998a-87f84a3625ad" 
                    className="center-align"
                >
                    <EnergyIcon
                        type={ENERGY_TYPES.BATTERY}
                        active={batteryActive}
                        iconSize={energyIconDiameter}
                        borderWidth={energyIconBorderWidth}
                        showIconImage={customIcons && customIcons[ENERGY_TYPES.BATTERY] == null}
                        innerIconView={customIcons ? customIcons[ENERGY_TYPES.BATTERY] : null}
                        inactiveColor={inactiveColor}
                        iconStyle={iconStyle}
                        iconContainerStyle={{
                            ...iconContainerStyle,
                            borderColor: COLORS.BATTERY
                        }}
                    />
                </div>
            );
        
        // Render the complete power flow component
        return (
            <div 
                data-testid="a9f4d12a-b2bc-4fb1-98d1-ba2246341d1a" 
                {...containerClassAttrs}
            >
                <div 
                    data-testid="7b3807df-ad55-4238-87d9-afc5737194aa" 
                    className="power-flow" 
                    style={style}
                >
                    {/* Render glowing effect for active icons */}
                    {this._getActiveGlowIcons(
                        activeIcons, 
                        gridWidth, 
                        gridHeight, 
                        energyIconDiameter, 
                        energyIconBorderWidth, 
                        activeGlowRadius, 
                        labelMargin, 
                        labelHeight, 
                        showPowerwall, 
                        showNegative
                    )}
                    
                    {/* Render power labels */}
                    {this._getPowerLabels(
                        activeTypes, 
                        availableTypes, 
                        showLabels, 
                        showZero, 
                        gridWidth, 
                        gridHeight, 
                        energyIconDiameter, 
                        energyIconBorderWidth, 
                        activeGlowRadius, 
                        labelMargin, 
                        labelHeight, 
                        labelWidth, 
                        customLabels, 
                        showPowerwall, 
                        showCompletePowerwall, 
                        displayPowers[ENERGY_TYPES.USAGE], 
                        displayPowers[ENERGY_TYPES.GRID], 
                        displayPowers[ENERGY_TYPES.SOLAR], 
                        displayPowers[ENERGY_TYPES.BATTERY], 
                        showNegative, 
                        units, 
                        handleInactiveLabelClick, 
                        handleNegativeLabelClick
                    )}
                    
                    <div 
                        data-testid="05dafaf8-fbb8-4519-8bc2-6578daea3b19" 
                        className="inner-container" 
                        style={{ marginTop: activeGlowRadius + labelHeight + labelMargin }}
                    >
                        {/* Solar icon */}
                        <div 
                            data-testid="1202100e-7a76-4479-a383-6b49dfec3fe9" 
                            className="center-align"
                        >
                            {solarIcon}
                        </div>
                        
                        {/* Grid row with arrows and home/usage icon */}
                        <div 
                            data-testid="060d9163-49c8-4cdf-a925-bf845b874ef2" 
                            className="grid-row-container"
                        >
                            {gridIcon}
                            <svg 
                                width={gridWidth} 
                                height={gridHeight} 
                                viewBox={`0 0 ${gridWidth} ${gridHeight}`}
                            >
                                {/* SVG definitions for arrows and paths */}
                                <defs>
                                    {/* Gradient definitions */}
                                    {GRADIENTS.BLUE_YELLOW}
                                    {GRADIENTS.YELLOW_GRAY}
                                    {GRADIENTS.GREEN_BLUE}
                                    {GRADIENTS.GREEN_GRAY}
                                    {GRADIENTS.GRAY_BLUE}
                                    {GRADIENTS.GRAY_GREEN}
                                    {GRADIENTS.YELLOW_GREEN}
                                    
                                    {/* Curved arrow definition */}
                                    <g id="curvedArrow" strokeWidth={lineWidth}>
                                        <path
                                            id="curvedPath"
                                            d={`M ${gridCenterX} ${0.75 * gridHeight}
                                              l 0 -${gridCenterY - lineRadius}
                                              a ${lineRadius},${lineRadius} 0 0 1 ${lineRadius},-${lineRadius}
                                              L ${gridWidth} ${0.25 * gridHeight}`}
                                            fill="none"
                                        />
                                        <circle
                                            data-testid="903be15b-24d0-4bc0-8231-33ba2a61fb5d"
                                            {...indicatorGlowCircleAttrs}
                                        >
                                            <animateMotion 
                                                dur={indicatorAnimationTimer + "ms"} 
                                                repeatCount="indefinite"
                                            >
                                                <mpath xlinkHref="#curvedPath" />
                                            </animateMotion>
                                        </circle>
                                        <circle
                                            data-testid="3aa17112-9f15-48d0-8ba5-7c8371e54eab"
                                            {...indicatorCircleAttrs}
                                        >
                                            <animateMotion 
                                                dur={indicatorAnimationTimer + "ms"} 
                                                repeatCount="indefinite"
                                            >
                                                <mpath xlinkHref="#curvedPath" />
                                            </animateMotion>
                                        </circle>
                                    </g>
                                    
                                    {/* Curved mirror arrow definition */}
                                    <g id="curvedArrowMirror" strokeWidth={lineWidth}>
                                        <path
                                            id="curvedPathMirror"
                                            d={`M 0 ${gridCenterY}
                                              l ${gridCenterX - lineRadius} 0
                                              a -${lineRadius},-${lineRadius} 0 0 1 ${lineRadius},${lineRadius}
                                              L ${gridCenterX} ${gridHeight}`}
                                            fill="none"
                                        />
                                        <circle
                                            data-testid="c488bfac-1dfc-49ae-b3c8-fa1933114c23"
                                            {...indicatorGlowCircleAttrs}
                                        >
                                            <animateMotion 
                                                dur={indicatorAnimationTimer + "ms"} 
                                                repeatCount="indefinite"
                                            >
                                                <mpath xlinkHref="#curvedPathMirror" />
                                            </animateMotion>
                                        </circle>
                                        <circle
                                            data-testid="ba7fb58a-0b65-4f1c-ac4b-ba2e8fb7e571"
                                            {...indicatorCircleAttrs}
                                        >
                                            <animateMotion 
                                                dur={indicatorAnimationTimer + "ms"} 
                                                repeatCount="indefinite"
                                            >
                                                <mpath xlinkHref="#curvedPathMirror" />
                                            </animateMotion>
                                        </circle>
                                    </g>
                                    
                                    {/* Horizontal arrow definition */}
                                    <g id="horizontalArrow" strokeWidth={lineWidth}>
                                        <path 
                                            id="horizontalPath" 
                                            d={`M 0 ${gridCenterY}
                                              L ${gridWidth} ${gridCenterY}`} 
                                            fill="none" 
                                        />
                                        <circle
                                            data-testid="9ebc49f0-40e3-43f4-9f52-a0e5adcfe894"
                                            {...indicatorGlowCircleAttrs}
                                        >
                                            <animateMotion 
                                                dur={indicatorAnimationTimer + "ms"} 
                                                repeatCount="indefinite"
                                            >
                                                <mpath xlinkHref="#horizontalPath" />
                                            </animateMotion>
                                        </circle>
                                        <circle
                                            data-testid="3300d987-ec99-4ea1-ada6-bde6ec36dfa7"
                                            {...indicatorCircleAttrs}
                                        >
                                            <animateMotion 
                                                dur={indicatorAnimationTimer + "ms"} 
                                                repeatCount="indefinite"
                                            >
                                                <mpath xlinkHref="#horizontalPath" />
                                            </animateMotion>
                                        </circle>
                                    </g>
                                    
                                    {/* Vertical arrow definition */}
                                    <g id="verticalArrow" strokeWidth={lineWidth}>
                                        <path 
                                            id="verticalPath" 
                                            d={`M ${gridCenterX} 0
                                              l 0 ${gridHeight}`} 
                                            fill="none" 
                                        />
                                        <circle
                                            data-testid="c4ec1b16-3575-4b16-b872-60500079629b"
                                            {...indicatorGlowCircleAttrs}
                                        >
                                            <animateMotion 
                                                dur={indicatorAnimationTimer + "ms"} 
                                                repeatCount="indefinite"
                                            >
                                                <mpath xlinkHref="#verticalPath" />
                                            </animateMotion>
                                        </circle>
                                        <circle
                                            data-testid="c4a076c4-5485-4fc2-86b3-ad8ee26be9c6"
                                            {...indicatorCircleAttrs}
                                        >
                                            <animateMotion 
                                                dur={indicatorAnimationTimer + "ms"} 
                                                repeatCount="indefinite"
                                            >
                                                <mpath xlinkHref="#verticalPath" />
                                            </animateMotion>
                                        </circle>
                                    </g>
                                    
                                    {/* Half vertical arrow definition */}
                                    <g id="halfVerticalArrow" strokeWidth={lineWidth}>
                                        <path 
                                            id="halfVerticalPath" 
                                            d={`M ${gridCenterX} ${gridCenterY}
                                              l 0 ${gridHeight}`} 
                                            fill="none" 
                                        />
                                        <circle
                                            data-testid="0ccc289b-a06d-4325-8b3e-6efb792b404b"
                                            {...indicatorGlowCircleAttrs}
                                        >
                                            <animateMotion 
                                                dur={indicatorAnimationTimer + "ms"} 
                                                repeatCount="indefinite"
                                            >
                                                <mpath xlinkHref="#halfVerticalPath" />
                                            </animateMotion>
                                        </circle>
                                        <circle
                                            data-testid="e337a015-54b6-4cd4-87dd-83c3c8c30314"
                                            {...indicatorCircleAttrs}
                                        >
                                            <animateMotion 
                                                dur={indicatorAnimationTimer + "ms"} 
                                                repeatCount="indefinite"
                                            >
                                                <mpath xlinkHref="#halfVerticalPath" />
                                            </animateMotion>
                                        </circle>
                                    </g>
                                </defs>
                                
                                {/* Power flow arrows */}
                                {batteryToHomeArrow}
                                {batteryToGridArrow}
                                {gridToHomeArrow}
                                {gridToBatteryArrow}
                                {solarToBatteryArrow}
                                {solarToGridArrow}
                                {solarToHomeArrow}
                                {inactiveSolarVerticalPath}
                                {inactiveGridHorizontalPath}
                                {batteryToLowerArrow}
                            </svg>
                            {usageIcon}
                        </div>
                        
                        {/* Powerwall or battery component */}
                        {powerwallOrBatteryComponent}
                        
                        {/* Grid services status indicator */}
                        {!compact && (
                            <GridServicesIndicator 
                                intl={this.props.intl} 
                                active={sitemasterRunning} 
                                gridServicesActive={gridServicesActive} 
                            />
                        )}
                        
                        {/* System control buttons */}
                        {this._getSitemasterControl()}
                    </div>
                    
                    {/* Islanded mode overlay */}
                    {this._getIslanded(
                        gridStatus, 
                        gridWidth, 
                        gridHeight, 
                        lineWidth, 
                        energyIconDiameter, 
                        energyIconBorderWidth, 
                        activeGlowRadius, 
                        labelMargin, 
                        labelHeight
                    )}
                </div>
            </div>
        );
    }
    
    // Generate class name for the power flow grid container
    _getPowerFlowGridClassName(showCompletePowerwall, sitemasterRunning, authenticated, gridServicesActive) {
        let className = "power-flow-grid";
        
        if (showCompletePowerwall) {
            className += " complete";
        }
        
        if (this.props.compact) {
            className += " compact";
        }
        
        if (authenticated) {
            className += " sitemaster";
        }
        
        if (sitemasterRunning) {
            className += " active";
            
            if (gridServicesActive && !this.props.compact) {
                className += " services";
            }
        }
        
        return className;
    }
    
    // Create glow effects for active energy icons
    _getActiveGlowIcons(activeIcons, gridWidth, gridHeight, iconSize, borderWidth, glowRadius, labelMargin, labelHeight, showPowerwall, showNegative) {
        let glowElements = [];
        const iconRadius = iconSize / 2;
        const gridCenterY = gridHeight / 2;
        const totalLabelHeight = labelMargin + labelHeight;
        
        // Filter and create glow elements for each active icon
        activeIcons
            .filter(type => {
                switch (type) {
                    case ENERGY_TYPES.USAGE:
                        return false;
                    case ENERGY_TYPES.SOLAR:
                        return !showNegative || this.props.solarPower > 0;
                    case ENERGY_TYPES.BATTERY:
                        return !showNegative || this.props.batteryPower > 0;
                    case ENERGY_TYPES.GRID:
                        return !showNegative || this.props.gridPower > 0;
                    default:
                        return false;
                }
            })
            .forEach((type, index) => {
                let styles = {};
                let containerStyles = {
                    width: iconSize + 2 * borderWidth,
                    height: iconSize + 2 * borderWidth,
                    borderRadius: iconRadius + glowRadius,
                    borderWidth: glowRadius
                };
                
                // Position the glow element based on icon type
                switch (type) {
                    case ENERGY_TYPES.SOLAR:
                        styles.top = totalLabelHeight;
                        styles.borderColor = COLORS.SOLAR;
                        styles.left = 0;
                        styles.right = 0;
                        break;
                    
                    case ENERGY_TYPES.GRID:
                        styles.top = iconRadius + gridCenterY + borderWidth + totalLabelHeight;
                        styles.right = gridWidth + 2 * iconRadius + 2 * borderWidth;
                        styles.borderColor = COLORS.GRID;
                        styles.left = 0;
                        break;
                    
                    case ENERGY_TYPES.BATTERY:
                        styles.top = iconSize + gridHeight + 2 * borderWidth + totalLabelHeight;
                        styles.borderColor = COLORS.BATTERY;
                        styles.left = 0;
                        styles.right = 0;
                        break;
                }
                
                // Skip certain glow elements for Powerwall
                if (!(showPowerwall && [ENERGY_TYPES.SOLAR, ENERGY_TYPES.GRID].includes(type))) {
                    glowElements.push(
                        <div 
                            data-testid="ff98e7cc-920d-4090-9053-b554d054b987" 
                            key={index} 
                            className="glow-container" 
                            style={{...containerStyles, ...styles}} 
                        />
                    );
                }
            });
        
        return glowElements;
    }
    
    // Create power labels for each component
    _getPowerLabels(
        activeTypes, 
        availableTypes, 
        showLabels, 
        showZero, 
        gridWidth, 
        gridHeight, 
        iconSize, 
        borderWidth, 
        glowRadius, 
        labelMargin, 
        labelHeight, 
        labelWidth, 
        customLabels, 
        showPowerwall, 
        showCompletePowerwall, 
        usagePower, 
        gridPower, 
        solarPower, 
        batteryPower, 
        showNegative, 
        units, 
        handleInactiveLabelClick, 
        handleNegativeLabelClick
    ) {
        if (!showLabels) {
            return [];
        }
        
        const totalLabelHeight = labelMargin + labelHeight;
        
        // Create labels for each energy type
        return ENERGY_TYPE_LIST.map((type, index) => {
            let powerValue = null;
            let labelContent = null;
            let customLabel = customLabels && customLabels[type] ? customLabels[type] : null;
            let labelStyles = { width: labelWidth };
            
            // Set label position and style based on type
            switch (type) {
                case ENERGY_TYPES.SOLAR:
                    powerValue = this.props.solarPower && solarPower;
                    labelStyles.top = 0;
                    labelStyles.left = 0;
                    labelStyles.right = 0;
                    labelStyles.color = COLORS.SOLAR;
                    break;
                
                case ENERGY_TYPES.GRID:
                    powerValue = this.props.gridPower && gridPower;
                    if (showPowerwall) {
                        labelStyles.top = 0.5 * iconSize + 0.5 * gridHeight + 2 * borderWidth;
                    } else {
                        labelStyles.top = 1.5 * iconSize + 0.5 * gridHeight + 3 * borderWidth + 
                                     totalLabelHeight + glowRadius + labelMargin;
                    }
                    labelStyles.left = 0;
                    labelStyles.right = gridWidth + iconSize + 2 * borderWidth;
                    labelStyles.color = COLORS.GRID;
                    break;
                
                case ENERGY_TYPES.BATTERY:
                    powerValue = this.props.batteryPower && batteryPower;
                    if (showPowerwall) {
                        labelStyles.top = gridHeight + totalLabelHeight + iconSize + 2 * borderWidth + 
                                      (showCompletePowerwall ? 108.5 : 19.5);
                    } else {
                        labelStyles.top = gridHeight + totalLabelHeight + 2 * iconSize + 4 * borderWidth + 
                                      labelMargin + glowRadius;
                        labelStyles.color = COLORS.BATTERY;
                    }
                    labelStyles.left = 0;
                    labelStyles.right = 0;
                    break;
                
                case ENERGY_TYPES.USAGE:
                    powerValue = this.props.loadPower && usagePower;
                    if (showPowerwall) {
                        labelStyles.top = 0.5 * iconSize + 0.5 * gridHeight + 2 * borderWidth;
                    } else {
                        labelStyles.top = 1.5 * iconSize + 0.5 * gridHeight + 3 * borderWidth + 
                                     totalLabelHeight + glowRadius + labelMargin;
                    }
                    labelStyles.left = gridWidth + iconSize + 2 * borderWidth;
                    labelStyles.right = 0;
                    labelStyles.color = COLORS.USAGE;
                    break;
            }
            
            // Check if type is missing or inactive
            const isMissingType = !availableTypes.includes(type);
            const isInactiveType = !activeTypes.includes(type);
            
            // Create appropriate icon for label status
            let statusIcon = null;
            
            if (isMissingType) {
                // Create delete icon for missing types
                statusIcon = (
                    <span
                        data-testid="dd3afd47-058d-409f-a862-ca980813739a"
                        id="missing-meter-label"
                        className="delete-icon"
                        onClick={() => {
                            handleInactiveLabelClick && handleInactiveLabelClick(ENERGY_TYPE_NAMES[type], true);
                        }}
                    >
                        ×
                    </span>
                );
            } else if (isInactiveType) {
                // Create info icon for inactive types
                statusIcon = (
                    <img
                        data-testid="ef571495-5054-451e-909f-0eb988f9552e"
                        id="inactive-image-label"
                        className="info sm hand label-image"
                        src={type === ENERGY_TYPES.BATTERY ? batteryInfoIcon : infoIcon}
                        onClick={() => {
                            handleInactiveLabelClick && handleInactiveLabelClick(ENERGY_TYPE_NAMES[type]);
                        }}
                        alt="Label Inactive"
                    />
                );
            }
            
            // Check if solar or usage is negative and needs warning icon
            const isSolar = type === ENERGY_TYPES.SOLAR;
            const negativeThreshold = isSolar && units === CONSTANTS.PowerUnits.WATTS ? -20 : 0;
            
            const negativeIcon = (isSolar || type === ENERGY_TYPES.USAGE) && 
                powerValue != null && powerValue < negativeThreshold
                ? (
                    <img
                        data-testid="9f44e874-0b91-4867-920c-5b3fce1648f3"
                        id="negative-image-label"
                        className="caution sm hand label-image"
                        src={warningIcon}
                        onClick={() => {
                            handleNegativeLabelClick && handleNegativeLabelClick(ENERGY_TYPE_NAMES[type]);
                        }}
                        alt="Label Negative"
                    />
                ) 
                : null;
            
            // Create label content if power value exists and meets display criteria
            if (powerValue != null && (showZero || (!showZero && powerValue !== 0))) {
                labelContent = (
                    <p data-testid="4c6aadb3-7661-4d7f-b1ff-d5a0571fac60">
                        {negativeIcon}
                        {statusIcon}
                        {statusIcon == null ? powerValue + " " : ""}
                        {isMissingType ? "" : units}
                    </p>
                );
            }
            
            // Return the complete label container
            return (
                <div 
                    data-testid="ec7d6a6d-b6d2-411c-a535-c052c00baf62"
                    key={index}
                    className={"label-container " + (isInactiveType && !isMissingType ? "label-inactive" : "")}
                    style={labelStyles}
                >
                    {customLabel}
                    {labelContent}
                </div>
            );
        });
    }
    
    // Create powerwall visualization with battery level
    _getPowerwall(showCompletePowerwall, iconSize, borderWidth, iconStyle, batteryPercentage, sitemasterRunning, noActiveTypes, isResiSystem) {
        let powerwallImage = null;
        let batteryLevelSvg = null;
        let batteryPercentageLabel = null;
        
        // Only show battery level if percentage is available
        if (batteryPercentage != null && (batteryPercentage !== 0 || !noActiveTypes)) {
            const fontHeight = 22;
            const strokeWidth = 2;
            const completeWidth = showCompletePowerwall ? 191 : 172;
            const completeHeight = showCompletePowerwall ? 267 : 94;
            const batteryHeight = showCompletePowerwall ? 212 : 94;
            const batteryX = showCompletePowerwall ? 172 : 157;
            
            // Create SVG for battery level visualization
            batteryLevelSvg = (
                <svg 
                    className="powerwall-soe" 
                    width={completeWidth} 
                    height={completeHeight} 
                    viewBox={`0 0 ${completeWidth} ${completeHeight}`}
                >
                    {/* Battery outline */}
                    <rect 
                        x={batteryX} 
                        y={strokeWidth} 
                        width="5" 
                        height={batteryHeight} 
                        style={{ strokeWidth: "1px", stroke: "gray", fill: "none" }} 
                    />
                    
                    {/* Battery fill level based on percentage */}
                    <rect 
                        x={batteryX} 
                        y={strokeWidth + (batteryHeight * (100 - batteryPercentage)) / 100} 
                        width="5" 
                        height={(batteryHeight * batteryPercentage) / 100} 
                        style={{ fill: COLORS.BATTERY }} 
                    />
                </svg>
            );
            
            // Create percentage label
            batteryPercentageLabel = (
                <div
                    data-testid="234320a0-eab5-4528-bc42-aab6c7282f13"
                    className="label-container soe-label"
                    style={{ 
                        top: Math.max(0, strokeWidth + (batteryHeight * (100 - batteryPercentage)) / 100 - fontHeight / 2), 
                        left: showCompletePowerwall 
                            ? 0.5 * this.props.gridWidth - iconSize + 191 
                            : completeWidth + (0.5 * this.props.gridWidth - iconSize) + 12, 
                        color: sitemasterRunning ? "white" : "black" 
                    }}
                >
                    {formatNumber(batteryPercentage, 0)}%
                </div>
            );
        }
        
        // Choose appropriate powerwall image based on configuration
        powerwallImage = showCompletePowerwall
            ? (
                <img 
                    data-testid="edc861a1-c692-487b-970c-16ca01bb74db" 
                    src={isResiSystem ? residentialPowerwallImage : commercialPowerwallImage} 
                    style={{ height: "267px", width: "191px" }} 
                />
            ) 
            : (
                <img 
                    data-testid="b3372156-8a9e-4d17-9721-fcc5891d1074" 
                    src={simplePowerwallImage} 
                    style={{ height: "94px", width: "172px" }} 
                />
            );
        
        // Return complete powerwall component
        return (
            <div 
                data-testid="03852a2e-1a99-4ed3-98e7-a98e292646eb" 
                className="center-align position-relative"
            >
                {batteryPercentageLabel}
                {batteryLevelSvg}
                {powerwallImage}
            </div>
        );
    }
    
    // Create overlay for islanded mode (off-grid)
    _getIslanded(gridStatus, gridWidth, gridHeight, lineWidth, iconSize, borderWidth, glowRadius, labelMargin, labelHeight) {
        if (gridStatus !== GRID_STATUS.ISLANDED && gridStatus !== GRID_STATUS.TRANSITION_TO_GRID) {
            return null;
        }
        
        const iconTotalSize = iconSize + 2 * borderWidth;
        
        // Return X overlay for islanded mode
        return (
            <div 
                data-testid="4ad39542-2910-4a3b-b987-2c25190ea97e" 
                className="islanded-container" 
                style={{ 
                    top: 0.5 * iconSize + 0.5 * gridHeight + borderWidth + glowRadius + labelMargin + labelHeight, 
                    left: 0, 
                    right: gridWidth + iconSize + 2 * borderWidth, 
                    width: iconTotalSize, 
                    height: iconTotalSize 
                }}
            >
                <svg width={iconTotalSize} height={iconTotalSize}>
                    <g>
                        {/* X lines for disconnected grid */}
                        <line 
                            x1="0" 
                            y1="0" 
                            x2={iconTotalSize} 
                            y2={iconTotalSize} 
                            stroke={COLORS.ISLANDED} 
                            strokeWidth={lineWidth} 
                        />
                        <line 
                            x1={iconTotalSize} 
                            y1="0" 
                            x2="0" 
                            y2={iconTotalSize} 
                            stroke={COLORS.ISLANDED} 
                            strokeWidth={lineWidth} 
                        />
                    </g>
                </svg>
            </div>
        );
    }
    
    // Create controls for system operation (start/stop, grid connection)
    _getSitemasterControl() {
        const { 
            isResi, 
            gridStatus, 
            sitemasterRunning, 
            authenticated, 
            compact, 
            criticalInstallationProblems 
        } = this.props;
        
        // Only show controls if authenticated
        if (!authenticated) {
            return null;
        }
        
        let startStopButton;
        let gridButton = null;
        let isGridConnectButton = false;
        
        // Set appropriate button for residential systems
        if (isResi) {
            switch (gridStatus) {
                case GRID_STATUS.CONNECTED:
                case null:
                case undefined:
                    isGridConnectButton = true;
                    gridButton = (
                        <FormattedMessage 
                            id="power_flow_view_go_off_grid" 
                            defaultMessage="GO OFF GRID" 
                        />
                    );
                    break;
                
                case GRID_STATUS.ISLANDED:
                    isGridConnectButton = false;
                    gridButton = (
                        <FormattedMessage 
                            id="power_flow_view_go_on_grid" 
                            defaultMessage="GO ON GRID" 
                        />
                    );
                    break;
                
                case GRID_STATUS.TRANSITION_TO_GRID:
                case GRID_STATUS.ISLAND_READY:
                default:
                    gridButton = (
                        <img 
                            className="spinner" 
                            src={spinnerImage} 
                            height={20} 
                            alt={LOCALIZED_STRINGS.gridButtonSpinnerAltLabel} 
                        />
                    );
                    break;
            }
        }
        
        // Create start/stop system button
        startStopButton = sitemasterRunning
            ? (
                <button 
                    type="button" 
                    className="btn btn-action btn-sitemaster center-block btn-stop" 
                    onClick={this._handleSitemanagerStartStopClick}
                >
                    <FormattedMessage 
                        id="power_flow_view_stop_system" 
                        defaultMessage="STOP SYSTEM" 
                    />
                </button>
            ) 
            : (
                <button 
                    type="button" 
                    className="btn btn-action btn-sitemaster center-block btn-start" 
                    onClick={this._handleSitemanagerStartStopClick}
                >
                    <FormattedMessage 
                        id="power_flow_view_start_system" 
                        defaultMessage="START SYSTEM" 
                    />
                </button>
            );
        
        const isGridButtonDisabled = !sitemasterRunning || !gridStatus;
        
        // If critical installation problems exist, show warnings and limited controls
        if (criticalInstallationProblems.length > 0) {
            return (
                <div>
                    {/* Show all critical installation problems */}
                    {criticalInstallationProblems.map((problem) => (
                        <InstallationProblem problem={problem} />
                    ))}
                    
                    {/* Only show stop button if system is running */}
                    {sitemasterRunning && startStopButton}
                </div>
            );
        }
        
        // Otherwise show full control panel
        return (
            <div className={compact ? "compact-btn-row" : ""}>
                {startStopButton}
                
                {/* Show grid connection button for residential systems */}
                {isResi && (
                    <div>
                        <button 
                            type="button" 
                            className={`btn btn-action btn-sitemaster center-block ${isGridConnectButton ? "btn-stop" : "btn-start"}`}
                            onClick={this._handleIslandingClick}
                            disabled={isGridButtonDisabled}
                        >
                            {gridButton}
                        </button>
                        
                        {/* Show explanation if grid button is disabled */}
                        {isGridButtonDisabled && !sitemasterRunning && !compact && (
                            <small className="text-muted disabled-explanation">
                                <FormattedMessage 
                                    id="power_flow_view_grid_button_disabled_reason" 
                                    defaultMessage="System must be started in order to go off grid." 
                                />
                            </small>
                        )}
                    </div>
                )}
            </div>
        );
    }
    
    // Handle start/stop button click
    _handleSitemanagerStartStopClick(event) {
        event.preventDefault();
        
        if (this.props.handleStartStopSitemanager) {
            this.props.handleStartStopSitemanager();
        }
    }
    
    // Handle grid connection button click
    _handleIslandingClick(event) {
        event.preventDefault();
        
        const { gridStatus } = this.props;
        
        if (gridStatus === GRID_STATUS.CONNECTED) {
            // Go off-grid if currently connected
            if (this.props.handleGoOffGrid) {
                this.props.handleGoOffGrid();
            }
        } else if (gridStatus === GRID_STATUS.ISLANDED) {
            // Reconnect to grid if currently islanded
            if (this.props.handleReconnectToGrid) {
                this.props.handleReconnectToGrid();
            }
        }
    }
}

// Define constants used throughout the component
const ENERGY_TYPES = {
    SOLAR: 'SOLAR',
    BATTERY: 'BATTERY',
    GRID: 'GRID',
    USAGE: 'USAGE'
};

const ENERGY_TYPE_NAMES = {
    SOLAR: 'Solar',
    BATTERY: 'Battery',
    GRID: 'Grid',
    USAGE: 'Usage'
};

const ENERGY_TYPE_LIST = [
    ENERGY_TYPES.SOLAR,
    ENERGY_TYPES.GRID,
    ENERGY_TYPES.BATTERY,
    ENERGY_TYPES.USAGE
];

const GRID_STATUS = {
    CONNECTED: 'CONNECTED',
    ISLANDED: 'ISLANDED',
    TRANSITION_TO_GRID: 'TRANSITION_TO_GRID',
    ISLAND_READY: 'ISLAND_READY'
};

const COLORS = {
    BATTERY: '#4CAF50', // Green
    GRID: '#9E9E9E',    // Gray
    SOLAR: '#FFC107',   // Yellow/Amber
    USAGE: '#2196F3',   // Blue
    INACTIVE: '#E0E0E0', // Light gray
    ISLANDED: '#F44336'  // Red
};

const GRADIENTS = {
    BLUE_YELLOW: (
        <linearGradient id="blueYellowGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor={COLORS.USAGE} />
            <stop offset="100%" stopColor={COLORS.SOLAR} />
        </linearGradient>
    ),
    YELLOW_GRAY: (
        <linearGradient id="yellowGrayGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor={COLORS.SOLAR} />
            <stop offset="100%" stopColor={COLORS.GRID} />
        </linearGradient>
    ),
    GREEN_BLUE: (
        <linearGradient id="greenBlueGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor={COLORS.BATTERY} />
            <stop offset="100%" stopColor={COLORS.USAGE} />
        </linearGradient>
    ),
    GREEN_GRAY: (
        <linearGradient id="greenGrayGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor={COLORS.BATTERY} />
            <stop offset="100%" stopColor={COLORS.GRID} />
        </linearGradient>
    ),
    GRAY_BLUE: (
        <linearGradient id="grayBlueGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor={COLORS.GRID} />
            <stop offset="100%" stopColor={COLORS.USAGE} />
        </linearGradient>
    ),
    GRAY_GREEN: (
        <linearGradient id="grayGreenGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor={COLORS.GRID} />
            <stop offset="100%" stopColor={COLORS.BATTERY} />
        </linearGradient>
    ),
    YELLOW_GREEN: (
        <linearGradient id="yellowGreenGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor={COLORS.SOLAR} />
            <stop offset="100%" stopColor={COLORS.BATTERY} />
        </linearGradient>
    )
};

const CONSTANTS = {
    METER_POWER_NOISE: 100, // Power reading noise threshold
    PowerUnits: {
        WATTS: 'W',
        KILOWATTS: 'kW',
        MEGAWATTS: 'MW'
    }
};

// Add the discharge threshold constant
PowerFlowVisualization.DISCHARGE_THRESHOLD = 100; // Minimum power for showing battery discharge to grid

export default PowerFlowVisualization;
