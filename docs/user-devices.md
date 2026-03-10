# User Devices - PCEventManager

## Team Device Profile
- **Primary devices:** Budget Android phones
- **Screen widths:** ~360-400px typical
- **Browser:** Chrome (Android default)
- **Secondary:** Some iPhones (Safari)
- **Supervisor:** Uses both desktop and mobile

## Testing Viewports (Priority Order)
1. **360x640** - Budget Android (Samsung Galaxy A series, Moto G) - PRIMARY
2. **375x667** - iPhone SE / older iPhones
3. **390x844** - iPhone 14 / modern phones
4. **412x915** - Pixel 7 / larger Androids
5. **768x1024** - iPad Mini (low priority)
6. **1280x800+** - Desktop (existing layout)

## Performance Considerations
- Budget Androids have limited RAM (2-4GB) and slower CPUs
- Minimize JavaScript bundle size
- Avoid heavy animations and transitions
- Lazy-load non-critical content
- Use system fonts where possible to reduce load time
- Keep DOM complexity low on list/table views
