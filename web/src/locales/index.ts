import en from './en'
import zh from './zh'
import type { LocaleMessages } from './en'

export type Locale = 'en' | 'zh'

export const messages: Record<Locale, LocaleMessages> = { en, zh }

export type { LocaleMessages }
