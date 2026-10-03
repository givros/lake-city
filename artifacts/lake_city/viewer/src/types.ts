export type Vec3 = [number,number,number];
export type Vec2 = [number,number];
export interface MaterialData { color:string|number; roughness?:number; metalness?:number }
export interface MeshData { material:string; positionOffset:number; positionCount:number; normalOffset:number; indexOffset:number; indexCount:number }
export interface Prototype { meshes:MeshData[]; collision:Vec2|null }
export interface Instance { id:string;prototype:string;position:Vec3;rotation:number;scale:Vec3;region:string }
export interface Landmark { id:string;name:string;position:Vec3;lookAt:Vec3;walkPosition?:Vec3 }
export interface CameraData { id:string;name:string;position:Vec3;target?:Vec3;lookAt?:Vec3 }
export interface CityData { materials:Record<string,MaterialData>;prototypes:Record<string,Prototype>;instances:Instance[];bounds:{min:Vec2;max:Vec2};waterPolygons:Vec2[][];waterHolePolygons?:Vec2[][];walkSurfaces?:{bounds:[number,number,number,number];height:number}[];paths:{id:string;points:Vec2[];width:number;closed:boolean}[];landmarks:Landmark[];cameras:CameraData[]|Record<string,CameraData>;stats:Record<string,number>;sourceHash:string }

export const VEHICLE_PROTOTYPES=new Set(['car_sedan','car_suv','delivery_van']);
