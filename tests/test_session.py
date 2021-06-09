import pytest
import pyama.session.model as pysm
import pyama.session.controller as pysc
import pyama.session.view_tk as pysvtk
import pyama.session.sessionopener_tk as pyssotk
class TestSession:
    @pytest.fixture
    def Controller(self):
        return pysc.SessionController()
    @pytest.fixture
    def View(self, Controller):
        view = pysvtk.SessionView_Tk(Controller.title, Controller.control_queue, Controller.status)
        Controller.view = view
        return view
    @pytest.fixture
    def Session(self, View, Controller):
        View._session_opener = pyssotk.SessionOpener(View.root, control_queue=View.control_queue, status=View.status)
        Controller.initialize_session()
        return Controller.sessions[Controller.view._session_opener.session_id]

    def test_controller_initialization(self, Controller):
        assert isinstance(Controller, pysc.SessionController)
    def test_view_initialization(self, Controller, View):
        assert isinstance(View, pysvtk.SessionView_Tk)
        assert Controller.view == View
    def test_session_initialization(self, Session):
        assert isinstance(Session, pysm.SessionModel)
