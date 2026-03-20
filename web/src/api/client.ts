import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

/**
 * Request a gateway restart after config changes.
 * Fire-and-forget: the server will terminate after responding.
 */
export async function restartGateway(): Promise<void> {
  try {
    await api.post('/gateway/restart')
  } catch {
    // Expected — the server shuts down, so the request may fail
  }
}

export default api
