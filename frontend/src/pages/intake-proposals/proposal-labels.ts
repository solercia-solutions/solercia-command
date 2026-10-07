import type {
  ConfidenceLevel,
  ProposalRelation,
  ProposalStatus,
} from '@entities/intake-proposal/intake-proposal.model';

type Variant = 'success' | 'warning' | 'danger' | 'info' | 'neutral';

/** Colores de las etiquetas de la bandeja: informan, no alarman (la confianza baja no es error). */
export const RELATION_VARIANT: Record<ProposalRelation, Variant> = {
  tarea_existente: 'info',
  tarea_nueva: 'warning',
  irrelevante: 'neutral',
};

export const CONFIDENCE_VARIANT: Record<ConfidenceLevel, Variant> = {
  alta: 'success',
  media: 'info',
  baja: 'neutral',
};

export const STATUS_VARIANT: Record<ProposalStatus, Variant> = {
  propuesta: 'info',
  aceptada: 'success',
  descartada: 'neutral',
};
