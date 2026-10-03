/** Resolve bundled resources under both localhost and the deployed project base. */
export const assetUrl=(path:string)=>`${import.meta.env.BASE_URL}assets/${path.replace(/^\/+/, '')}`;
