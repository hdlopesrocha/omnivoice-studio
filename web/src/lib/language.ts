import type { Language } from './types'

export const PORTUGUESE_VARIANTS = new Set(['pt-PT', 'pt-BR'])

export const PORTUGUESE_VARIANT_OPTIONS: Language[] = [
  {
    id: 'pt-PT',
    name: 'Portuguese (Portugal)',
    iso: 'por',
    hours: 0,
    variant_of: 'pt',
    requires_voice: true,
  },
  {
    id: 'pt-BR',
    name: 'Portuguese (Brazil)',
    iso: 'por',
    hours: 0,
    variant_of: 'pt',
    requires_voice: true,
  },
]

export function isPortugueseVariant(language: string | null | undefined): boolean {
  return Boolean(language && PORTUGUESE_VARIANTS.has(language))
}

export function modelLanguage(language: string | null | undefined): string | null {
  if (!language) return null
  return isPortugueseVariant(language) ? 'pt' : language
}

export function languageVariant(language: string | null | undefined): string | null {
  return isPortugueseVariant(language) ? (language as string) : null
}

export function previewTextForLanguage(
  language: string | null | undefined,
): string | undefined {
  if (language === 'pt-PT') {
    return 'Olá! Esta é uma pré-visualização da minha voz em português de Portugal.'
  }
  if (language === 'pt-BR') {
    return 'Olá! Esta é uma prévia da minha voz em português do Brasil.'
  }
  return undefined
}
