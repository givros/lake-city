# City source contract

World units are metres. X east, Y up, Z south. Reference 1450 x 1088 pixels: X=(u-725)*1.5, Z=(v-544)*1.5. Ground Y=0. Prototype bases Y=0. Building primary facade faces +Z. Rotations are Y Euler radians, right handed. All dimensions are full dimensions.

Python generators expose `build_architecture(scene)` or `build_landscape_assets(scene)` and call `scene.prototype(name, parts, collision=None)` where collision is [half_width,half_depth] for a solid building. Parts are dictionaries:

- box: {shape:'box',size:[w,h,d],position:[x,y,z],material:'name',rotation:[rx,ry,rz] (optional)}
- cylinder: {shape:'cylinder',radius:r, radiusTop:r (optional),height:h,segments:12,position:[x,y,z],material:'name',rotation:[rx,ry,rz] (optional)}; local cylinder axis Y.
- sphere: {shape:'sphere',radius:r,segments:10,rings:6,position:[x,y,z],scale:[sx,sy,sz] (optional),material:'name'}
- mesh: {shape:'mesh',vertices:[[x,y,z],...],faces:[[i,j,k],...],material:'name'}

Parts may have a semantic `name`. `scene.material(name, color, roughness=0.8, metalness=0.0)` registers a hex sRGB material. Opaque only; glass is opaque reflective blue for non-enterable buildings. Emit physically credible detailed source geometry, dimensions and many varied prototypes. Do not produce placements: the main layout owns them.

The viewer receives public/assets/city.json and geometry.bin. city.json has materials dictionary; prototypes dictionary name -> {meshes:[{material,positionOffset,positionCount,normalOffset,indexOffset,indexCount}],collision:[hx,hz] or null}; instances array {id,prototype,position:[x,y,z],rotation:radians,scale:[x,y,z],region}; bounds {min:[x,z],max:[x,z]}; waterPolygons array of arrays [x,z]; paths array {id,points:[[x,z],...],width,closed}; landmarks array {id,name,position:[x,y,z],lookAt:[x,y,z]}; cameras; stats; sourceHash.

Binary arrays use byte offsets, Float32 positions/normals and Uint32 indices. positionCount is total floats, indexCount total indices. Arrays have 4-byte alignment. Every mesh has one material. No compression. Prototype meshes are identical between Blender and runtime. Instance transforms use Y rotation and non-uniform scale. Invisible collision rectangles derive from prototype collision and transformed scale. Trees use trunk collision only if provided. Water blocks foot movement except explicit bridge walk surfaces stored separately.

Additional optional walkSurfaces: {bounds:[minX,minZ,maxX,maxZ],height} for bridges/docks. Default ground height=0.15. Map bounds are soft forest boundaries; constrain inside world bounds.
