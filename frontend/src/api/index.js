import client from './client'

export const login = (data) => client.post('/admin/login', data)
export const getMe = () => client.get('/admin/me')
export const changePassword = (data) => client.put('/admin/password', data)

export const getStats = () => client.get('/dashboard/stats')

export const listSources = (params) => client.get('/sources', { params })
export const createSource = (data) => client.post('/sources', data)
export const getSource = (id) => client.get(`/sources/${id}`)
export const updateSource = (id, data) => client.put(`/sources/${id}`, data)
export const deleteSource = (id) => client.delete(`/sources/${id}`)
export const syncSource = (id) => client.post(`/sources/${id}/sync`)
export const syncAllSources = () => client.post('/sources/sync-all')

export const listNodes = (params) => client.get('/nodes', { params })
export const createNode = (data) => client.post('/nodes', data)
export const getNode = (id) => client.get(`/nodes/${id}`)
export const updateNode = (id, data) => client.put(`/nodes/${id}`, data)
export const deleteNode = (id) => client.delete(`/nodes/${id}`)
export const batchNodes = (data) => client.post('/nodes/batch', data)
export const importNodes = (data) => client.post('/nodes/import', data)

export const listPackages = () => client.get('/packages')
export const createPackage = (data) => client.post('/packages', data)
export const getPackage = (id) => client.get(`/packages/${id}`)
export const updatePackage = (id, data) => client.put(`/packages/${id}`, data)
export const deletePackage = (id) => client.delete(`/packages/${id}`)
export const regenerateToken = (id) => client.post(`/packages/${id}/regenerate-token`)
export const togglePackage = (id) => client.post(`/packages/${id}/toggle`)
export const previewPackage = (id) => client.get(`/packages/${id}/preview`)

export const getLogs = (params) => client.get('/logs', { params })

export const getSystemSettings = () => client.get('/system/settings')
export const updateSystemSettings = (data) => client.put('/system/settings', data)
