#!/usr/bin/env python3
"""Check every placed STEP for validity and penetration into the drilled PCB body."""
import json
import render_svg as r


def main():
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.BRepCheck import BRepCheck_Analyzer
    r.load_occ()
    board_path = r.resolve_board()
    board = r.parse_board(board_path.read_text())
    body, thickness = r.board_body(board)
    loaded, rows = {}, []
    for fp in r.children(board,'footprint'):
        for model in r.children(fp,'model'):
            if 'hide' in model:
                continue
            path = r.model_path(model,board_path,r.TOOL_DIR/'.models'/r.MODEL_REV,False)
            if path not in loaded:
                reader = r.Reader()
                if reader.ReadFile(str(path)) != r.Done or reader.TransferRoots() == 0:
                    raise ValueError(f'Cannot read {path}')
                loaded[path] = reader.OneShape()
            part = r.placed_model(loaded[path],model,fp,thickness)
            box = Bnd_Box()
            BRepBndLib.AddOptimal_s(part,box)
            common = BRepAlgoAPI_Common(body,part)
            if not common.IsDone():
                raise ValueError(f'Cannot check board intersection: {r.reference(fp)}')
            properties = GProp_GProps()
            BRepGProp.VolumeProperties_s(common.Shape(),properties)
            rows.append(dict(reference=r.reference(fp),model=path.name,
                        bounds_mm=[round(v,5) for v in box.Get()],
                        valid=BRepCheck_Analyzer(part).IsValid(),
                        board_intersection_mm3=round(properties.Mass(),7)))
    failures = [row for row in rows if not row['valid'] or row['board_intersection_mm3'] > .00001]
    report = dict(models=len(rows),unique_files=len(loaded),failures=len(failures),components=rows)
    out = board_path.parent/'renders/svg/model-audit.json'
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2)+'\n')
    print(f'{len(rows)} placed models / {len(loaded)} STEP files / {len(failures)} failures: {out}')
    for row in failures:
        print(row)
    return bool(failures)


if __name__ == '__main__':
    raise SystemExit(main())
