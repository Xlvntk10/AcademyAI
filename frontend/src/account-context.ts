export type AccountUser = { id: string; email: string; namespace: string }
export type AccountSession = { mode: 'local' | 'supabase'; user: AccountUser | null }
let user: AccountUser | null = null
let namespace = ''
let access = true

export function setAccountContext(account: AccountUser | null, canConnect = true) {
  user = account
  namespace = account?.namespace ?? ''
  access = canConnect
}
export const accountUser = () => user
export const accountNamespace = () => namespace
export const canConnect = () => access
export const privateKey = (key: string) => namespace ? `${key}:${namespace}` : key
