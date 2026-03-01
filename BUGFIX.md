# CityScout Button Bug — Root Cause & Fix

## Problem
Los botones "Try Demo" y "Use Sample" no respondían. El browser console mostraba:
```
Failed to load resource: the server responded with a status of 500 ()
/_next/static/chunks/646e023070791660.js
```

## Root Cause
**Turbopack bug en Next.js 16** con imports de CSS de librerías que no soportan SSR (como Leaflet).

El fragmento `import "leaflet/dist/leaflet.css"` en `layout.tsx` causaba que Turbopack generara un chunk fantasma (`646e023070791660.js`) que no existía en el build output. Cuando el browser intentaba cargarlo, el server tiraba 500 error, rompiendo todo el JS de la app.

## Fix Aplicado
1. Removí `import "leaflet/dist/leaflet.css"` de `app/layout.tsx`
2. Reemplacé con CDN link en `<head>`:
   ```html
   <link
     rel="stylesheet"
     href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
     integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY="
     crossOrigin=""
   />
   ```
3. También removí el duplicate import en `CityMap.tsx`
4. Rebuild completo (`rm -rf .next && npm run build`)

## Files Modified
- `web/app/layout.tsx`
- `web/app/components/CityMap.tsx`

## URLs Activas (después del fix)
- Frontend: `https://anymore-butter-classes-bedford.trycloudflare.com`
- API: `https://spring-samuel-hybrid-included.trycloudflare.com`

## Referencias
- Issue similar: https://github.com/vercel/next.js/issues/77036
- Turbopack + dynamic imports = problemas conocidos en Next.js 16
