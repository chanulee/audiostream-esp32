"""Read STEP/XDE face colors without discarding assembly and solid inheritance."""
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorType
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDF import TDF_LabelSequence
from OCP.Quantity import Quantity_Color
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_SOLID
from OCP.TopoDS import TopoDS_Compound,TopoDS_Iterator
from OCP.XCAFPrs import XCAFPrs,XCAFPrs_IndexedDataMapOfShapeStyle
from OCP.TopLoc import TopLoc_Location
import render_svg as r


def read_colored_step(path):
    document = TDocStd_Document(TCollection_ExtendedString('BinXCAF'))
    reader = STEPCAFControl_Reader()
    reader.SetColorMode(True)
    if reader.ReadFile(str(path)) != r.Done or not reader.Transfer(document):
        raise ValueError(f'Cannot read STEP colors: {path}')
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    colors = XCAFDoc_DocumentTool.ColorTool_s(document.Main())
    roots = TDF_LabelSequence()
    shapes.GetFreeShapes(roots)
    compound = TopoDS_Compound();builder=r.Builder();builder.MakeCompound(compound)
    inherited = {}
    appearances=XCAFPrs_IndexedDataMapOfShapeStyle()
    for i in range(1,roots.Length()+1):
        XCAFPrs.CollectStyleSettings_s(roots.Value(i),TopLoc_Location(),appearances)
    # Some STEP assemblies attach styles to unlocated solids while free shapes
    # carry instance locations. Propagate their face styles through TShape identity.
    style_faces={}
    for i in range(1,appearances.Extent()+1):
        shape=appearances.FindKey(i);style=appearances.FindFromIndex(i)
        if not style.IsSetColorSurf():continue
        c=style.GetColorSurf();value=[round(v,7) for v in (c.Red(),c.Green(),c.Blue())]
        priority=3 if shape.ShapeType()==TopAbs_FACE else 2 if shape.ShapeType()==TopAbs_SOLID else 1
        faces=[shape] if shape.ShapeType()==TopAbs_FACE else []
        explorer=TopExp_Explorer(shape,TopAbs_FACE)
        while explorer.More():faces.append(explorer.Current());explorer.Next()
        for face in faces:
            key=hash(face.Located(TopLoc_Location()))
            if key not in style_faces or priority>style_faces[key][0]:style_faces[key]=(priority,value)

    def color(shape, fallback):
        if appearances.Contains(shape):
            style=appearances.FindFromKey(shape)
            if style.IsSetColorSurf():
                c=style.GetColorSurf()
                return [round(v,7) for v in (c.Red(),c.Green(),c.Blue())]
        c = Quantity_Color()
        for kind in (XCAFDoc_ColorType.XCAFDoc_ColorSurf,XCAFDoc_ColorType.XCAFDoc_ColorGen):
            if colors.GetColor(shape,kind,c) or colors.GetInstanceColor(shape,kind,c):
                return [round(v,7) for v in (c.Red(),c.Green(),c.Blue())]
        candidate=style_faces.get(hash(shape.Located(TopLoc_Location())))
        if candidate:return candidate[1]
        return fallback

    def inherit(shape, fallback=None):
        current=color(shape,fallback)
        if shape.ShapeType()==TopAbs_FACE:
            inherited[hash(shape)]=current
            return
        iterator=TopoDS_Iterator(shape)
        while iterator.More():
            inherit(iterator.Value(),current);iterator.Next()
    for i in range(1,roots.Length()+1):
        root = shapes.GetShape_s(roots.Value(i))
        builder.Add(compound,root)
        inherit(root)
    values=[];specified=0
    faces=TopExp_Explorer(compound,TopAbs_FACE)
    while faces.More():
        face=faces.Current();c=color(face,inherited.get(hash(face)))
        specified+=c is not None
        values.append(c if c is not None else [.2,.2,.2]);faces.Next()
    return compound,values,dict(faces=len(values),colored_faces=specified)


def scene_mesh(board,board_path,mesh_data):
    body,thickness=r.board_body(board)
    scene=mesh_data(body)
    scene['board']=[1.]*(len(scene['triangles'])//3)
    loaded={};stats={}
    for fp in r.children(board,'footprint'):
        for model in r.children(fp,'model'):
            if 'hide' in model:continue
            path=r.model_path(model,board_path,r.TOOL_DIR/'.models'/r.MODEL_REV,False)
            if path not in loaded:
                print('Reading STEP colors:',path.name,flush=True)
                loaded[path]=read_colored_step(path)
                stats[path.name]=loaded[path][2]
            raw,colors,_=loaded[path]
            part=r.placed_model(raw,model,fp,thickness)
            data=mesh_data(part,colors)
            for key in ('triangles','lines','clean_lines','normals','colors'):scene[key].extend(data[key])
            scene['board'].extend([0.]*(len(data['triangles'])//3))
    scene['color_sources']=stats
    return scene
