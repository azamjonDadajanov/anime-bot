// Admin panel is served from its own host (admin.anichopar.uz) at the site
// root; on the main domain the same SPA still nests it under /admin — except
// production, where nginx blocks that path. Every admin link goes through
// these helpers so one build works in both layouts.
export function isAdminHost() {
  return window.location.hostname.startsWith('admin.')
}

export function adminBase() {
  return isAdminHost() ? '' : '/admin'
}

export function adminPath(path = '/') {
  const base = adminBase()
  const suffix = path.startsWith('/') ? path : `/${path}`
  if (!base) return suffix || '/'
  return `${base}${suffix === '/' ? '' : suffix}` || base
}
