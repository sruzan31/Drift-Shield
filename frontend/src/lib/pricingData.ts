export interface PricingPlan {
  id: string;
  title: string;
  price: string;
  badge?: string;
  description: string;
  note: string;
  buttonLabel?: string;
  buttonLink?: string;
}

export const pricingPlans: PricingPlan[] = [
  {
    id: 'starter',
    title: 'Starter',
    price: 'Free',
    description: 'For individuals exploring DriftShield locally.',
    note: 'Uses your own computing resources.',
    buttonLabel: 'Open workspace',
    buttonLink: '/app',
  },
  {
    id: 'team',
    title: 'Team Pilot',
    price: '₹999/month',
    badge: 'Planned — proposed launch price',
    description: 'For small teams evaluating model-performance monitoring.',
    note: 'This plan is not yet available for purchase.',
  },
  {
    id: 'enterprise',
    title: 'Enterprise',
    price: 'Starting at ₹4,999/month',
    badge: 'Planned — proposed launch price',
    description: 'For organizations seeking deployment, integration, and support tailored to their requirements.',
    note: 'Final pricing depends on usage, hosting, and support requirements. This plan is not yet available for purchase.',
  },
];
