CSS = """
window.panel {{ background-color: {crust}; }}
.panel button {{ min-height: 48px; min-width: 48px; padding: 0; margin: 4px 1px; border-radius: 12px;
    background-color: transparent; }}
/* no hover colour: on a touch screen it sticks to whatever was tapped last */
.panel button:hover {{ background-color: transparent; }}
.panel button:active {{ background-color: {raised}; }}
.panel button.apps:hover {{ background-color: {accent}; }}
.panel button.arrow:hover {{ background-color: {base}; }}
.panel button.status:hover {{ background-color: {card}; }}
.panel button.task.active:hover, .panel button.on:hover {{ background-color: {raised}; }}
.panel button .icon {{ font-size: 24px; }}
.panel button.apps {{ background-color: {accent}; color: {crust}; margin-left: 4px; }}
.panel button.arrow {{ min-width: 36px; background-color: {base}; }}
.panel button.arrow:disabled {{ opacity: 0.3; }}
.panel button.task.active {{ background-color: {raised}; box-shadow: inset 0 -3px {accent}; }}
.panel button.task.minimized {{ opacity: 0.55; }}
.panel button.on {{ color: {accent}; background-color: {raised}; }}
.panel button.status {{ padding: 0 14px; border-radius: 24px; background-color: {card}; margin-right: 4px; }}
.panel button.status .icon {{ font-size: 19px; }}
.panel .clock {{ font-weight: bold; }}
.panel .divider {{ min-width: 1px; margin: 16px 5px; background-color: {hover}; }}

window.overlay, window.home, window.osd {{ background-color: transparent; }}
.backdrop {{ background-color: alpha({crust}, 0.55); }}
.backdrop.solid {{ background-color: alpha({crust}, 0.97); }}
.sheet {{ background-color: {base}; border: 1px solid {hover}; border-radius: 20px; padding: 14px; }}
.sheet .tile {{ border-radius: 16px; min-height: 72px; padding: 4px; }}
.sheet .tile .icon {{ font-size: 24px; }}
.sheet .tile label {{ font-size: 13px; }}
.sheet .tile.on {{ background-color: {accent}; color: {crust}; }}
.sheet .wide {{ min-height: 62px; border-radius: 16px; padding: 0 12px; }}
.sheet .wide.on {{ background-color: {accent}; color: {crust}; }}
.sheet .wide.on .sub {{ color: {crust}; }}
.sheet .mode {{ min-height: 44px; padding: 0 4px; font-size: 13px; }}
.sheet .mode.on {{ background-color: {accent}; color: {crust}; }}
.sheet .big {{ min-height: 64px; font-size: 17px; }}
.launcher entry {{ min-height: 50px; font-size: 17px; }}
.launcher button.app {{ padding: 8px 2px; border-radius: 16px; background-color: transparent; }}
.launcher button.app:hover {{ background-color: {raised}; }}
.launcher button.app label {{ font-size: 13px; }}
.launcher flowboxchild {{ padding: 0; background-color: transparent; }}

.home .greeting {{ font-size: 30px; font-weight: bold; color: {bright}; }}
.home button.machine {{ background-color: alpha({card}, 0.94); border-radius: 16px; padding: 10px 14px; }}
.home button.machine:hover {{ background-color: {raised}; }}
.home button.machine .name {{ font-size: 18px; font-weight: bold; }}
.home button.machine .icon {{ font-size: 30px; }}
.home .dot {{ font-size: 15px; color: {faint}; }}
.home .dot.good {{ color: {green}; }}
.home .dot.error {{ color: {red}; }}
.home .dot.warn {{ color: {yellow}; }}
.home .panelcard {{ background-color: alpha({card}, 0.92); border-radius: 18px; }}
.home flowboxchild {{ padding: 0; background-color: transparent; }}

.osd .box {{ background-color: {card}; border-radius: 22px; padding: 12px 20px; }}
.osd .icon {{ font-size: 24px; }}
.osd progressbar trough, .osd progressbar progress {{ min-height: 10px; border-radius: 6px; border: none; }}
.osd progressbar trough {{ background-color: {hover}; }}
.osd progressbar progress {{ background-color: {accent}; }}
"""
